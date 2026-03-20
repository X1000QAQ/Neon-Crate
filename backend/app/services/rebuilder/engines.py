from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)

from app.services.rebuilder.rebuild_utils import (
    _calc_tv_target_path,
    _cleanup_empty_dirs,
    _get_physical_siblings,
    _get_sibling_episodes,
    _locate_video_for_task,
    _nuclear_clean_directory,
)


class BaseRebuildEngine:
    def __init__(self, db, meta_manager, background_tasks=None):
        self.db = db
        self.meta_manager = meta_manager
        self.background_tasks = background_tasks

    def _parse_video_exts(self) -> frozenset:
        raw = self.db.get_config("supported_video_exts", "")
        parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
        parts = [e if e.startswith(".") else f".{e}" for e in parts]
        if parts:
            return frozenset(parts)
        return frozenset(
            {
                ".mkv",
                ".mp4",
                ".avi",
                ".ts",
                ".m2ts",
                ".mov",
                ".wmv",
                ".flv",
                ".rmvb",
                ".webm",
                ".iso",
                ".vob",
                ".mpg",
                ".mpeg",
                ".m4v",
            }
        )

    def _safe_delete_metadata_files(self, metadata_dir: str, library_root: str) -> dict:
        resolved_meta = Path(metadata_dir).resolve()
        resolved_lib = Path(library_root).resolve()
        try:
            resolved_meta.relative_to(resolved_lib)
        except ValueError:
            raise PermissionError(f"[SECURITY] metadata_dir '{metadata_dir}' 不在 library_root '{library_root}' 内")

        deleted: dict = {"poster": [], "fanart": [], "ai_subtitles": []}
        for pattern, category in [("poster.*", "poster"), ("fanart.*", "fanart")]:
            for f in resolved_meta.glob(pattern):
                try:
                    f.resolve().relative_to(resolved_meta)
                except ValueError:
                    continue
                if f.is_file():
                    f.unlink()
                    deleted[category].append(str(f))
        for f in resolved_meta.iterdir():
            if not f.is_file():
                continue
            try:
                f.resolve().relative_to(resolved_meta)
            except ValueError:
                continue
            if re.search(r"\.ai\.", f.name, re.IGNORECASE):
                f.unlink()
                deleted["ai_subtitles"].append(str(f))
        return deleted

    def _schedule_subtitle_now(
        self,
        *,
        task_record: dict,
        tmdb_id: Optional[int],
        imdb_id: str,
        target_path: str,
        media_type: str,
        is_archive: bool,
        task_id: int,
    ) -> None:
        if not self.background_tasks:
            return

        async def _run_subtitle_now():
            try:
                api_key = self.db.get_config("os_api_key", "").strip()
                ua = self.db.get_config("os_user_agent", "SubtitleHunter v13.2")
                if not api_key:
                    return
                from app.services.subtitle import SubtitleEngine

                engine = SubtitleEngine(api_key=api_key, user_agent=ua)
                try:
                    result = await asyncio.wait_for(
                        engine.download_subtitle_for_task(
                            db_manager=self.db,
                            file_path=task_record.get("path") or target_path,
                            tmdb_id=str(tmdb_id) if tmdb_id else None,
                            media_type=media_type,
                            imdb_id=imdb_id or None,
                            target_path=target_path,
                            archive_id=task_id if is_archive else None,
                        ),
                        timeout=60.0,
                    )
                    ok = isinstance(result, str) and (
                        result.startswith("成功") or "跳过" in result or "已有" in result
                    )
                    new_sub_status = "scraped" if ok else "missing"
                    try:
                        if not is_archive and task_id:
                            self.db.update_task_sub_status(task_id, new_sub_status)
                        elif is_archive and task_id:
                            self.db.update_archive_sub_status(
                                task_id,
                                sub_status=new_sub_status,
                                last_check=time.strftime("%Y-%m-%d %H:%M:%S"),
                            )
                    except Exception as e:
                        logger.error(f"Subtitle task failed for {task_id}: {str(e)}")
                        # 尝试回写失败状态，不让前端干等
                        try:
                            self.db.update_any_task_metadata(task_id, is_archive, sub_status="failed")
                        except Exception as e2:
                            logger.error(f"Subtitle task failed for {task_id}: {str(e2)}")
                except asyncio.TimeoutError:
                    if task_id and is_archive:
                        try:
                            self.db.update_archive_sub_status(
                                task_id,
                                sub_status="failed",
                                last_check=time.strftime("%Y-%m-%d %H:%M:%S"),
                            )
                        except Exception as e:
                            logger.error(f"Subtitle task failed for {task_id}: {str(e)}")
                            # 尝试回写失败状态，不让前端干等
                            try:
                                self.db.update_any_task_metadata(task_id, is_archive, sub_status="failed")
                            except Exception as e2:
                                logger.error(f"Subtitle task failed for {task_id}: {str(e2)}")
                    elif not is_archive and task_id:
                        try:
                            self.db.update_task_sub_status(task_id, "failed")
                        except Exception as e:
                            logger.error(f"Subtitle task failed for {task_id}: {str(e)}")
                            # 尝试回写失败状态，不让前端干等
                            try:
                                self.db.update_any_task_metadata(task_id, is_archive, sub_status="failed")
                            except Exception as e2:
                                logger.error(f"Subtitle task failed for {task_id}: {str(e2)}")
            except Exception as e:
                logger.error(f"Subtitle task failed for {task_id}: {str(e)}")
                # 尝试回写失败状态，不让前端干等
                try:
                    self.db.update_any_task_metadata(task_id, is_archive, sub_status="failed")
                except Exception as e2:
                    logger.error(f"Subtitle task failed for {task_id}: {str(e2)}")
                return

        self.background_tasks.add_task(_run_subtitle_now)


class NuclearEngine(BaseRebuildEngine):
    def execute(self, task: Dict[str, Any], body: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        # NuclearEngine：全量重建语义；TV Series/Season 多集批量路径与单集 / 电影单文件主轴并存。
        # 旧址处置：Series/Season 尾相为沿父链级联空目录清理（Cascading Purge）；Episode/Movie 尾相为自旧址向上的轻量空目录回收。
        rebuilt: Dict[str, Any] = {"nfo": False, "poster": False, "subtitle": "skipped", "nuclear": False}

        media_type: str = context["media_type"]
        scope: str = context["scope"]
        new_tmdb_id: Optional[int] = context.get("new_tmdb_id")
        new_imdb_id: str = context.get("new_imdb_id") or ""
        new_title: str = context.get("new_title") or ""
        new_year: str = context.get("new_year") or ""
        metadata_dir: str = context["metadata_dir"]
        library_root: str = context["library_root"]

        if not new_tmdb_id:
            raise HTTPException(status_code=400, detail="api_error_missing_tmdb_id")

        # 语义路由：全量重建轨道；不经 Patch 护盾，直接重写物理布局与元数据产物
        db_video_exts = self._parse_video_exts()

        if media_type == "tv" and scope in ("series", "season"):
            if not new_imdb_id:
                raise HTTPException(status_code=400, detail="[NUCLEAR] missing_imdb_id")

            season_num = None
            if scope == "season":
                season_num = int(context.get("task_season") or 1)

            sibs_physical = _get_physical_siblings(metadata_dir, season_num, db_video_exts)
            if not sibs_physical:
                raise HTTPException(status_code=400, detail=f"[NUCLEAR][{scope.upper()}] 物理扫描未发现视频文件: {metadata_dir}")

            # DB 反向映射（物理路径 → 记录），用于循环内 DB 更新
            _active_recs = self.db.get_all_data(include_ignored=True) or []
            for _r in _active_recs: _r["is_archive"] = False
            _archived_recs = self.db.get_archived_data() or []
            for _r in _archived_recs: _r["is_archive"] = True
            all_recs = _active_recs + _archived_recs
            path_to_rec: dict = {}
            for _r in all_recs:
                _p = _r.get("target_path") or _r.get("path")
                if _p:
                    try:
                        path_to_rec[Path(_p).resolve()] = _r
                    except Exception:
                        pass

            # 数据契约：library_root 已由上游白名单纠偏；show_root 计算锁定单层目录语义，禁止路径栈叠
            lib_parent = library_root

            # 提前构造 show_root 供金标同化预检使用
            safe_title = re.sub(r'[\\/:*?"<>|]', "_", new_title.strip())
            show_root = Path(lib_parent) / (f"{safe_title} ({new_year})" if new_year else safe_title)
            show_root.mkdir(parents=True, exist_ok=True)
            series_nfo = str(show_root / "tvshow.nfo")

            # 金标同化预检：必须在循环前，确保 DB 写入使用正确 ID
            if scope == "season" and Path(series_nfo).exists():
                from app.services.metadata.nfo_parser import parse_nfo as _parse_nfo
                try:
                    _gold = _parse_nfo(series_nfo)
                    if _gold and _gold.get("tmdb_id"):
                        new_tmdb_id = int(_gold["tmdb_id"])
                        new_imdb_id = _gold.get("imdb_id") or new_imdb_id
                        logger.info(f"[NUCLEAR] 季核爆金标同化预检: tmdb={new_tmdb_id}, imdb={new_imdb_id}")
                except (ValueError, TypeError, Exception):
                    pass

            old_roots: set[Path] = set()
            moved_count = 0
            rebuilt["episode_nfos"] = {}
            rebuilt["episode_moved"] = {}
            pending_db_updates: list = []  # 暂存 DB 更新，等基建完成后统一回写

            for ep_phys in sibs_physical:
                ep_src = ep_phys["path"]
                ep_s = ep_phys["season"]
                ep_e = ep_phys["episode"]
                old_ep_path = Path(ep_src)

                # 1. [锚定源文件] -> 2. [拔除旧伴生 NFO] -> 3. [压入待清理池]
                old_nfo = old_ep_path.with_suffix(".nfo")
                if old_nfo.exists():
                    try:
                        old_nfo.unlink()
                        logger.info(f"[CLEANUP] 核爆清障，已移除旧 NFO: {old_nfo}")
                    except OSError as e:
                        logger.warning(f"[CLEANUP] 旧 NFO 移除失败，可能导致目录残留: {e}")

                old_roots.add(old_ep_path.parent)

                ep_ext = Path(ep_src).suffix
                ep_new_path = _calc_tv_target_path(lib_parent, new_title, new_year, ep_s, ep_e, ep_ext)
                Path(ep_new_path).parent.mkdir(parents=True, exist_ok=True)

                ep_key = f"S{ep_s:02d}E{ep_e:02d}"
                if Path(ep_src).resolve() != Path(ep_new_path).resolve():
                    if Path(ep_new_path).exists():
                        continue
                    import shutil

                    shutil.move(ep_src, ep_new_path)
                    moved_count += 1
                else:
                    ep_new_path = ep_src

                # 强制重建单集 NFO
                ep_nfo = str(Path(ep_new_path).with_suffix(".nfo"))
                if Path(ep_nfo).exists():
                    Path(ep_nfo).unlink()
                ep_nfo_ok = self.meta_manager.generate_episode_nfo(
                    tmdb_id=str(new_tmdb_id),
                    season=ep_s,
                    episode=ep_e,
                    output_path=ep_nfo,
                    title=new_title,
                )
                rebuilt["episode_nfos"][ep_key] = ep_nfo_ok

                # 暂存 DB 更新（不立即写入，等待 local_poster 已知后统一回写）
                _rec = path_to_rec.get(Path(ep_src).resolve())
                if _rec:
                    pending_db_updates.append({
                        "id": _rec["id"],
                        "is_archive": _rec.get("is_archive", False),
                        "target_path": ep_new_path,
                        "season": ep_s,
                        "episode": ep_e,
                    })
                rebuilt["episode_moved"][ep_key] = ep_new_path

            # ==========================================
            # 剧集基建：Series 暴力重塑 vs Season 拓荒同化
            # ==========================================
            if scope == "series":
                # Series 权限：暴力摧毁并重建基建
                if Path(series_nfo).exists():
                    Path(series_nfo).unlink()
                rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", series_nfo, new_title, new_year))
                for pn in ["poster.jpg", "poster.png", "poster.webp", "fanart.jpg", "fanart.png", "fanart.webp"]:
                    p = show_root / pn
                    if p.exists():
                        p.unlink()
                self.meta_manager.download_poster(str(new_tmdb_id), "tv", str(show_root), new_title)
                try:
                    self.meta_manager.download_fanart(str(new_tmdb_id), "tv", str(show_root), new_title)
                except Exception:
                    pass

            elif scope == "season":
                if not Path(series_nfo).exists():
                    # 场景 A：荒野拓荒
                    logger.info(f"[NUCLEAR] 季核爆触发荒野拓荒: {show_root}")
                    self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", series_nfo, new_title, new_year)
                    self.meta_manager.download_poster(str(new_tmdb_id), "tv", str(show_root), new_title)
                    try:
                        self.meta_manager.download_fanart(str(new_tmdb_id), "tv", str(show_root), new_title)
                    except Exception:
                        pass
                # 场景 B：金标同化已在循环前完成，此处绝对不触碰海报和总 NFO

            rebuilt["season_posters"] = {}
            seasons_seen: set[int] = set()
            for ep in sibs_physical:
                s = ep.get("season")
                if s is None:
                    continue
                try:
                    s_int = int(s)
                except Exception:
                    continue
                if s_int in seasons_seen:
                    continue
                seasons_seen.add(s_int)
                sp = self.meta_manager.download_season_poster(str(new_tmdb_id), s_int, str(show_root), new_title)
                rebuilt["season_posters"][f"season{s_int:02d}"] = bool(sp)

            # 探测 show_root 实际海报路径（基建完成后才能知晓）
            local_poster: Optional[str] = None
            for _ext in [".jpg", ".png", ".webp"]:
                _p = show_root / f"poster{_ext}"
                if _p.exists():
                    local_poster = str(_p)
                    break
            rebuilt["poster"] = bool(local_poster)

            # 统一批量回写 DB（含 local_poster_path、clean_name 等完整字段）
            for upd in pending_db_updates:
                self.db.update_any_task_metadata(
                    upd["id"],
                    upd["is_archive"],
                    target_path=upd["target_path"],
                    season=upd["season"],
                    episode=upd["episode"],
                    tmdb_id=new_tmdb_id,
                    imdb_id=new_imdb_id or None,
                    title=new_title or None,
                    year=new_year or None,
                    clean_name=new_title or None,
                    local_poster_path=local_poster,
                )

            # 1. [级联空目录清理（Cascading Purge）] -> 2. [自各集旧址目录起沿父链上溯至 library_root 边界]
            # 3. [每层扫描视频生命体征：存活则空目录回收并终止上溯；无存活的则整目录核平后继续上溯]
            _lib_root_path = Path(library_root).resolve()
            for r in old_roots:
                current_dir = r.resolve()
                while (
                    current_dir != _lib_root_path
                    and current_dir.parent != current_dir
                    and _lib_root_path in current_dir.parents
                ):
                    if not current_dir.exists():
                        current_dir = current_dir.parent
                        continue

                    _has_vids = False
                    try:
                        for f in current_dir.rglob("*"):
                            if f.is_file() and f.suffix.lower() in db_video_exts:
                                _has_vids = True
                                break
                    except OSError:
                        pass

                    if _has_vids:
                        try:
                            _cleanup_empty_dirs(current_dir, _lib_root_path)
                        except OSError:
                            pass
                        break
                    else:
                        try:
                            import shutil

                            shutil.rmtree(current_dir)
                            logger.info(f"[CLEANUP] ☢️ 废弃媒体目录已彻底核平: {current_dir}")
                        except OSError as e:
                            logger.error(f"[CLEANUP] ❌ 拆除失败（可能存在锁定）: {current_dir} -> {e}")
                            break

                    current_dir = current_dir.parent

            rebuilt["nuclear"] = True
            nuclear_scope_msg_map = {
                "series": "msg_rebuild_success_nuclear_series",
                "season": "msg_rebuild_success_nuclear_season",
            }
            return {"success": True, "rebuilt": rebuilt, "message": nuclear_scope_msg_map.get(scope, "msg_rebuild_success_nuclear_tv_episode")}

        # 语义路由：Episode / Movie 单文件主轴（与 Series/Season 多集循环并列；同属全量重建语义）
        old_video_path = _locate_video_for_task(task, db_video_exts, metadata_dir)
        if not old_video_path:
            raise HTTPException(status_code=400, detail=f"[NUCLEAR] 无法定位视频文件: task_id={task.get('id')}")

        new_video_path = old_video_path
        try:
            import shutil

            task_season = context.get("task_season")
            task_episode = context.get("task_episode")

            if media_type == "tv" and task_season is not None and task_episode is not None:
                # 物理流转：单集目标路径基于 library_root 绝对坐标计算，与 Series/Season 分支路径语义对齐
                ep_ext = Path(old_video_path).suffix
                new_video_path = _calc_tv_target_path(
                    library_root, new_title, new_year,
                    int(task_season), int(task_episode), ep_ext
                )
                Path(new_video_path).parent.mkdir(parents=True, exist_ok=True)

                if Path(old_video_path).resolve() != Path(new_video_path).resolve():
                    if not Path(new_video_path).exists():
                        shutil.move(old_video_path, new_video_path)
                        # 1. [锚定旧址] -> 2. [拔除伴生 NFO] -> 3. [释放目录回收锁]
                        _old_path_obj = Path(old_video_path)
                        _old_nfo = _old_path_obj.with_suffix(".nfo")
                        if _old_nfo.exists():
                            try:
                                _old_nfo.unlink()
                                logger.debug(f"[CLEANUP] 单点核爆命中旧 NFO 清除: {_old_nfo}")
                            except OSError:
                                pass
                    else:
                        # 目标已存在（同路径），直接使用
                        new_video_path = old_video_path

                rebuilt["nuclear"] = True

            elif media_type == "movie":
                # 电影主轴：按规范片名（年）重命名并迁入目标目录
                rebuilt["nuclear"] = True

                safe_title = re.sub(r"[\\/:*?\"<>|]", "_", new_title.strip())
                year_str = f" ({new_year})" if new_year else ""
                ep_ext = Path(old_video_path).suffix
                new_name = f"{safe_title}{year_str}{ep_ext}"
                expected_dir = f"{safe_title}{year_str}"

                # 目标目录：library_root / Movie (Year) /
                new_movie_dir = Path(library_root) / expected_dir
                new_movie_dir.mkdir(parents=True, exist_ok=True)
                new_video_path = str(new_movie_dir / new_name)

                if Path(old_video_path).resolve() != Path(new_video_path).resolve():
                    if not Path(new_video_path).exists():
                        shutil.move(old_video_path, new_video_path)
                        # 1. [前置清障] -> 2. [拔除伴生与专属 NFO] -> 3. [释放目录回收锁]
                        _old_path_obj = Path(old_video_path)
                        _old_dir = _old_path_obj.parent
                        _old_nfo = _old_path_obj.with_suffix(".nfo")
                        if _old_nfo.exists():
                            try:
                                _old_nfo.unlink()
                                logger.debug(f"[CLEANUP] 单点核爆命中旧 NFO 清除: {_old_nfo}")
                            except OSError:
                                pass

                        if media_type == "movie":
                            _movie_nfo = _old_dir / "movie.nfo"
                            if _movie_nfo.exists():
                                try:
                                    _movie_nfo.unlink()
                                except OSError:
                                    pass
                        # 1. [目录占用扫描] -> 2. [探测是否仍有其他视频存活] -> 3. [有存活则中止级联清理]
                        _has_other_videos = False
                        try:
                            for f in _old_dir.rglob("*"):
                                if f.is_file() and f.suffix.lower() in db_video_exts:
                                    _has_other_videos = True
                                    break
                        except OSError:
                            pass

                        # 1. [边界锁定与核平] -> 2. [确认不越界] -> 3. [安全执行整包删除]
                        _old_dir_resolved = _old_dir.resolve()
                        _lib_root_path = Path(library_root).resolve()
                        _new_parent_path = Path(new_video_path).parent.resolve()
                        if _has_other_videos:
                            logger.warning(f"[CLEANUP] ⚠️ 探测到旧目录仍有其他视频文件，拒绝爆破: {_old_dir}")
                        elif _old_dir_resolved != _lib_root_path and _old_dir_resolved != _new_parent_path:
                            try:
                                shutil.rmtree(_old_dir)
                                logger.info(f"[CLEANUP] ☢️ 废弃电影目录已彻底核平: {_old_dir}")
                            except OSError as e:
                                logger.error(f"[CLEANUP] ❌ 拆除失败（可能存在权限不足或进程锁定）: {_old_dir} -> {e}")
                    else:
                        logger.warning(f"[NUCLEAR] 电影目标已存在，跳过搬运并保留原路径: {new_video_path}")
                        new_video_path = old_video_path

                # 数据契约：若物理搬运未发生，metadata_dir 必须锚定当前视频真实所在目录，禁止元数据与视频分离
                metadata_dir = str(Path(new_video_path).parent)

            else:
                # 未知媒体类型兜底：原地清理
                _nuclear_clean_directory(
                    metadata_dir, library_root,
                    video_exts=db_video_exts, protect_metadata=False
                )
                rebuilt["nuclear"] = True

            # 同步 DB target_path
            self.db.update_any_task_metadata(task["id"], context["is_archive"], target_path=new_video_path)

        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"api_error_nuclear_reset_failed: {e}")

        # 基建重写：NFO / 海报 / fanart 全量再生（全量重建轨道，不经 Patch 护盾）
        if media_type == "tv":
            # 确保写到剧集根
            md = os.path.dirname(os.path.abspath(new_video_path))
            if re.match(r"^(Season|S)\s*\d+$|^Specials$", os.path.basename(md), re.IGNORECASE):
                md = os.path.dirname(md)
            metadata_dir = md
            # 双轨隔离：单集主轴仅写 episode NFO；tvshow.nfo 由剧集根级流程独占，禁止在本分支覆盖
            ts, te = context.get("task_season"), context.get("task_episode")
            if ts is not None and te is not None:
                ep_nfo_path = str(Path(new_video_path).with_suffix(".nfo"))
                if Path(ep_nfo_path).exists():
                    Path(ep_nfo_path).unlink()
                rebuilt["episode_nfo"] = bool(
                    self.meta_manager.generate_episode_nfo(
                        tmdb_id=str(new_tmdb_id),
                        season=int(ts),
                        episode=int(te),
                        output_path=ep_nfo_path,
                        title=new_title,
                    )
                )
        else:
            nfo_path = os.path.join(metadata_dir, "movie.nfo")
            if Path(nfo_path).exists():
                Path(nfo_path).unlink()
            rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "movie", nfo_path, new_title, new_year))

        # ==========================================
        # 核心机制：荒野拓荒 (Bootstrap) vs 金标同化 (Assimilation)
        # ==========================================
        local_poster: Optional[str] = None
        is_tv_episode = (media_type == "tv" and scope == "episode")
        series_nfo_path = os.path.join(metadata_dir, "tvshow.nfo")

        if is_tv_episode:
            if not Path(series_nfo_path).exists():
                # 场景 A：荒野拓荒 (目标目录为全新，赋予单集越权建设权)
                logger.info(f"[NUCLEAR] 触发荒野拓荒，为新剧集创建基建: {metadata_dir}")
                self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", series_nfo_path, new_title, new_year)
                local_poster = self.meta_manager.download_poster(str(new_tmdb_id), media_type, metadata_dir, new_title)
                try:
                    self.meta_manager.download_fanart(str(new_tmdb_id), media_type, metadata_dir, new_title)
                except Exception:
                    pass
            else:
                # 场景 B：金标同化 (目标目录已有剧集，强制继承老大哥的 ID)
                from app.services.metadata.nfo_parser import get_tvshow_gold_standard
                gold_meta = get_tvshow_gold_standard(new_video_path)
                if gold_meta and gold_meta.get("tmdb_id"):
                    try:
                        # 类型契约：TMDB ID 规范为整型以匹配持久化层 schema
                        new_tmdb_id = int(gold_meta.get("tmdb_id"))
                        new_imdb_id = gold_meta.get("imdb_id") or new_imdb_id
                        logger.info(f"[NUCLEAR] 触发金标同化，单集继承主剧集身份: tmdb={new_tmdb_id}, imdb={new_imdb_id}")
                    except (ValueError, TypeError):
                        pass

                # 探测已有海报，回填给数据库（不重新下载）
                for p_name in ["poster.jpg", "poster.png", "poster.webp"]:
                    if (Path(metadata_dir) / p_name).exists():
                        local_poster = str(Path(metadata_dir) / p_name)
                        break
        else:
            # 电影轨道：海报与 fanart 全量清理后自 TMDB 重新拉取
            for name in ["poster.jpg", "poster.png", "poster.webp", "fanart.jpg", "fanart.png", "fanart.webp"]:
                p = Path(metadata_dir) / name
                if p.exists():
                    p.unlink()
            local_poster = self.meta_manager.download_poster(str(new_tmdb_id), media_type, metadata_dir, new_title)
            try:
                self.meta_manager.download_fanart(str(new_tmdb_id), media_type, metadata_dir, new_title)
            except Exception:
                pass

        rebuilt["poster"] = bool(local_poster)

        # 原子回写：合并 tmdb / 海报路径 / 目标路径等字段至双表之一
        self.db.update_any_task_metadata(
            task["id"],
            context["is_archive"],
            tmdb_id=new_tmdb_id,
            imdb_id=new_imdb_id or None,
            title=new_title or None,
            year=new_year or None,
            local_poster_path=local_poster or None,
            clean_name=new_title or None,
            season=context.get("task_season") if media_type == "tv" else None,
            episode=context.get("task_episode") if media_type == "tv" else None,
            target_path=new_video_path,
        )

        # 1. [单文件尾相：目录回收] -> 2. [自视频旧址父目录起向上回收空壳] -> 3. [止于 library_root；与 Series/Season 尾相级联清理互补（轻量空目录链）]
        try:
            _old_dir = Path(old_video_path).parent
            _cleanup_empty_dirs(_old_dir, Path(library_root))
        except Exception:
            pass

        single_nuclear_msg = "msg_rebuild_success_nuclear_movie" if media_type == "movie" else "msg_rebuild_success_nuclear_tv_episode"
        return {"success": True, "rebuilt": rebuilt, "message": single_nuclear_msg}


class AssetPatchEngine(BaseRebuildEngine):
    def execute(self, task: Dict[str, Any], body: Any, context: Dict[str, Any]) -> Dict[str, Any]:
        # AssetPatchEngine：补录（Patch）语义；Movie / TV 双轨隔离执行，scope 驱动 NFO 与海报策略分化。
        # 防误杀护盾：path_changed 门控物理位移与旧址 NFO 拆除；is_subtitle_only 门控基建 I/O，避免误伤未变更路径侧车文件。
        rebuilt: Dict[str, Any] = {"nfo": False, "poster": False, "subtitle": "skipped", "nuclear": False}

        media_type: str = context["media_type"]
        scope: str = context["scope"]
        new_tmdb_id: Optional[int] = context.get("new_tmdb_id")
        new_imdb_id: str = context.get("new_imdb_id") or ""
        new_title: str = context.get("new_title") or ""
        new_year: str = context.get("new_year") or ""
        metadata_dir: str = context["metadata_dir"]
        library_root: str = context["library_root"]
        target_path: str = context["target_path"]
        db_video_exts = self._parse_video_exts()
        old_video_path = _locate_video_for_task(task, db_video_exts, metadata_dir)
        if not old_video_path:
            old_video_path = target_path

        # 1. [模式推断] -> 2. [提取防误杀护盾标志 path_changed / is_subtitle_only] -> 3. [context 不含 rebuild_type 时由 body.refix_* 推导业务子模式]
        path_changed = str(old_video_path) != str(target_path)
        is_subtitle_only = bool(getattr(body, "refix_subtitle", False)) and not getattr(
            body, "refix_nfo", False
        ) and not getattr(body, "refix_poster", False)

        # 1. [语义路由] -> 2. 锚定路径边界并建立双轨执行门
        old_parent = Path(old_video_path).parent
        library_root = self.db.get_config(f"{media_type}_library_root", "") or os.path.dirname(os.path.dirname(old_video_path))

        # 1. [防误杀护盾 · 物理流转] -> 2. [仅 path_changed 且目标可写时执行 shutil.move] -> 3. [旧址伴生 NFO 仅在 move 成功后拆除；路径未变则禁止 unlink]
        try:
            if path_changed and Path(old_video_path).exists():
                import shutil

                Path(target_path).parent.mkdir(parents=True, exist_ok=True)
                if not Path(target_path).exists():
                    shutil.move(old_video_path, target_path)
                    old_nfo = Path(old_video_path).with_suffix(".nfo")
                    if old_nfo.exists():
                        try:
                            old_nfo.unlink()
                            logger.debug(f"[CLEANUP] AssetPatch 拆除旧址 NFO: {old_nfo}")
                        except OSError:
                            pass
                else:
                    target_path = old_video_path
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"api_error_patch_move_failed: {e}")

        # ==========================================
        # 金标同化（Gold Standard Assimilation）
        # 数据契约：海报 / 字幕等网络侧重试以磁盘 tvshow.nfo 为权威；DB 缓存不参与 TMDB / IMDb 身份裁决
        # ==========================================
        tv_show_root = Path(target_path).parent
        if media_type == "tv" and target_path:
            from app.services.metadata.nfo_parser import get_tvshow_gold_standard

            # 追溯 show root（优先有 tvshow.nfo 的目录）
            _probe_start = Path(target_path).parent
            _probe_chain = [_probe_start, *_probe_start.parents]
            for _cand in _probe_chain:
                if (_cand / "tvshow.nfo").exists():
                    tv_show_root = _cand
                    break

            gold_meta = get_tvshow_gold_standard(target_path)
            if gold_meta and gold_meta.get("tmdb_id"):
                try:
                    new_tmdb_id = int(gold_meta.get("tmdb_id"))
                    new_imdb_id = gold_meta.get("imdb_id") or new_imdb_id
                    logger.info(f"[PATCH] 金标同化成功，使用本地物理 ID: tmdb={new_tmdb_id}, imdb={new_imdb_id}")
                except (ValueError, TypeError):
                    pass

        # 执行契约：任一 refix_* 勾选即进入补录主流程；服务端不对用户意图做静默短路
        if (getattr(body, "refix_poster", False) or getattr(body, "refix_subtitle", False) or getattr(body, "refix_nfo", False)) and not new_tmdb_id:
            raise HTTPException(status_code=400, detail="api_error_missing_tmdb_id")

        local_poster: Optional[str] = None

        # 1. [语义路由] -> 2. 基于 media_type 的双轨隔离
        if media_type == "movie":
            movie_root = str(Path(target_path).parent)
            metadata_dir = movie_root

            # 防误杀护盾 · 基建门控：纯字幕子模式跳过电影轨 NFO / 海报基建，削减无关磁盘写入
            if not is_subtitle_only:
                if getattr(body, "refix_nfo", False) and new_tmdb_id:
                    if not getattr(body, "nuclear_reset", False):
                        try:
                            self._safe_delete_metadata_files(metadata_dir, library_root)
                        except PermissionError as e:
                            raise HTTPException(status_code=403, detail=str(e))
                    nfo_path = os.path.join(metadata_dir, "movie.nfo")
                    if Path(nfo_path).exists():
                        Path(nfo_path).unlink()
                    rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "movie", nfo_path, new_title, new_year))

                if getattr(body, "refix_poster", False) and new_tmdb_id:
                    for name in ["poster.jpg", "poster.png", "poster.webp", "fanart.jpg", "fanart.png", "fanart.webp"]:
                        p = Path(metadata_dir) / name
                        if p.exists():
                            p.unlink()
                    self.meta_manager.download_poster(str(new_tmdb_id), "movie", metadata_dir, new_title)
                    try:
                        self.meta_manager.download_fanart(str(new_tmdb_id), "movie", metadata_dir, new_title)
                    except Exception:
                        pass

            if getattr(body, "refix_subtitle", False):
                rebuilt["subtitle"] = "triggered"
                self.db.update_any_task_metadata(task["id"], context["is_archive"], sub_status="pending")
                self._schedule_subtitle_now(
                    task_record=task,
                    tmdb_id=new_tmdb_id,
                    imdb_id=new_imdb_id,
                    target_path=target_path,
                    media_type=media_type,
                    is_archive=context["is_archive"],
                    task_id=task["id"],
                )

            # 1. [物理海报探测] -> 2. Movie 仅在电影根目录探测 poster.*（纯字幕模式跳过）
            if not is_subtitle_only:
                target_dir = Path(target_path).parent
                for _ext in [".jpg", ".png", ".webp"]:
                    _p = target_dir / f"poster{_ext}"
                    if _p.exists():
                        local_poster = str(_p)
                        break

            message = "rebuild_complete:patch:movie"

        elif media_type == "tv":
            if re.match(r"^(Season|S)\s*\d+$|^Specials$", os.path.basename(metadata_dir), re.IGNORECASE):
                metadata_dir = os.path.dirname(metadata_dir)
            metadata_dir = str(tv_show_root if tv_show_root else Path(metadata_dir))

            # 防误杀护盾 · 基建门控：纯字幕子模式跳过 TV 轨 NFO / 海报基建；Movie/TV 双轨边界保持不变
            if not is_subtitle_only:
                if getattr(body, "refix_nfo", False) and new_tmdb_id:
                    if not getattr(body, "nuclear_reset", False):
                        try:
                            self._safe_delete_metadata_files(metadata_dir, library_root)
                        except PermissionError as e:
                            raise HTTPException(status_code=403, detail=str(e))

                    tvshow_nfo_path = os.path.join(metadata_dir, "tvshow.nfo")
                    if scope == "series":
                        if Path(tvshow_nfo_path).exists():
                            Path(tvshow_nfo_path).unlink()
                        rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", tvshow_nfo_path, new_title, new_year))
                    elif scope == "season":
                        if not Path(tvshow_nfo_path).exists():
                            rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", tvshow_nfo_path, new_title, new_year))
                    elif scope == "episode":
                        # 单集轨道严禁覆盖 tvshow.nfo，仅允许荒野拓荒
                        if not Path(tvshow_nfo_path).exists():
                            rebuilt["nfo"] = bool(self.meta_manager.generate_nfo(str(new_tmdb_id), "tv", tvshow_nfo_path, new_title, new_year))

                    ts, te = context.get("task_season"), context.get("task_episode")
                    if ts is not None and te is not None:
                        ep_nfo_path = str(Path(target_path).with_suffix(".nfo"))
                        if Path(ep_nfo_path).exists():
                            Path(ep_nfo_path).unlink()
                        rebuilt["episode_nfo"] = bool(
                            self.meta_manager.generate_episode_nfo(
                                tmdb_id=str(new_tmdb_id),
                                season=int(ts),
                                episode=int(te),
                                output_path=ep_nfo_path,
                                title=new_title,
                            )
                        )

                    if scope in ("series", "season"):
                        _sn = int(context.get("task_season") or 1) if scope == "season" else None
                        _sibs_nfo = _get_physical_siblings(metadata_dir, _sn, self._parse_video_exts())
                        rebuilt["episode_nfos"] = {}
                        for _ep in _sibs_nfo:
                            _ep_s = _ep["season"]
                            _ep_e = _ep["episode"]
                            _ep_path = _ep["path"]
                            _ep_nfo = str(Path(_ep_path).with_suffix(".nfo"))
                            if Path(_ep_nfo).exists():
                                Path(_ep_nfo).unlink()
                            _ep_ok = self.meta_manager.generate_episode_nfo(
                                tmdb_id=str(new_tmdb_id),
                                season=int(_ep_s),
                                episode=int(_ep_e),
                                output_path=_ep_nfo,
                                title=new_title,
                            )
                            rebuilt["episode_nfos"][f"S{int(_ep_s):02d}E{int(_ep_e):02d}"] = bool(_ep_ok)

                if getattr(body, "refix_poster", False) and new_tmdb_id:
                    if scope == "series":
                        for name in ["poster.jpg", "poster.png", "poster.webp", "fanart.jpg", "fanart.png", "fanart.webp"]:
                            p = Path(metadata_dir) / name
                            if p.exists():
                                p.unlink()
                        self.meta_manager.download_poster(str(new_tmdb_id), "tv", metadata_dir, new_title)
                        try:
                            self.meta_manager.download_fanart(str(new_tmdb_id), "tv", metadata_dir, new_title)
                        except Exception:
                            pass

                    if scope in ("season", "series"):
                        rebuilt["season_posters"] = {}
                        if scope == "season":
                            _s = int(context.get("task_season") or 1)
                            sp = self.meta_manager.download_season_poster(str(new_tmdb_id), _s, metadata_dir, new_title)
                            rebuilt["season_posters"][f"season{_s:02d}"] = bool(sp)
                        else:
                            _phys_all = _get_physical_siblings(metadata_dir, None, self._parse_video_exts())
                            seasons_seen: set[int] = set()
                            for _ep in _phys_all:
                                _s = _ep["season"]
                                if _s in seasons_seen:
                                    continue
                                seasons_seen.add(_s)
                                sp = self.meta_manager.download_season_poster(str(new_tmdb_id), _s, metadata_dir, new_title)
                                rebuilt["season_posters"][f"season{_s:02d}"] = bool(sp)

            if getattr(body, "refix_subtitle", False):
                rebuilt["subtitle"] = "triggered"
                if scope in ("season", "series"):
                    _sub_season = int(context.get("task_season") or 1) if scope == "season" else None
                    _phys_sibs = _get_physical_siblings(metadata_dir, _sub_season, self._parse_video_exts())
                    _active_recs = self.db.get_all_data(include_ignored=True) or []
                    for _r in _active_recs:
                        _r["is_archive"] = False
                    _archived_recs = self.db.get_archived_data() or []
                    for _r in _archived_recs:
                        _r["is_archive"] = True
                    _all_recs = _active_recs + _archived_recs
                    _path_to_rec: dict = {}
                    for _r in _all_recs:
                        _p = _r.get("target_path") or _r.get("path")
                        if _p:
                            try:
                                _path_to_rec[Path(_p).resolve()] = _r
                            except Exception:
                                pass
                    rebuilt["subtitle_triggered"] = 0
                    for _phys_ep in _phys_sibs:
                        _ep_path = _phys_ep["path"]
                        _rec = _path_to_rec.get(Path(_ep_path).resolve())
                        _task_id = _rec["id"] if _rec else 0
                        _is_arc = _rec.get("is_archive", False) if _rec else context["is_archive"]
                        if _task_id:
                            self.db.update_any_task_metadata(_task_id, _is_arc, sub_status="pending")
                        self._schedule_subtitle_now(
                            task_record={"path": _ep_path},
                            tmdb_id=new_tmdb_id,
                            imdb_id=new_imdb_id,
                            target_path=_ep_path,
                            media_type=media_type,
                            is_archive=_is_arc,
                            task_id=_task_id,
                        )
                        rebuilt["subtitle_triggered"] += 1
                else:
                    self.db.update_any_task_metadata(task["id"], context["is_archive"], sub_status="pending")
                    self._schedule_subtitle_now(
                        task_record=task,
                        tmdb_id=new_tmdb_id,
                        imdb_id=new_imdb_id,
                        target_path=target_path,
                        media_type=media_type,
                        is_archive=context["is_archive"],
                        task_id=task["id"],
                    )

            # 1. [物理海报探测] -> 2. TV 按金标同化追溯 show root 后探测 poster.*（纯字幕模式跳过）
            if not is_subtitle_only:
                probe_dir = tv_show_root if tv_show_root else Path(metadata_dir)
                for _ext in [".jpg", ".png", ".webp"]:
                    _p = probe_dir / f"poster{_ext}"
                    if _p.exists():
                        local_poster = str(_p)
                        break

            message = f"rebuild_complete:patch:tv:{scope}"

        else:
            raise HTTPException(status_code=400, detail=f"api_error_unsupported_media_type:{media_type}")

        rebuilt["poster"] = bool(local_poster)

        # 1. [原子回写] -> 2. [双表元数据与 target_path / local_poster_path 等同事务语义写入] -> 3. [尾相：旧址父链空目录向上回收（Patch 轻量回收，区别于全量重建尾相）]
        if new_tmdb_id:
            self.db.update_any_task_metadata(
                task["id"],
                context["is_archive"],
                target_path=target_path,
                tmdb_id=new_tmdb_id,
                imdb_id=new_imdb_id or None,
                title=new_title or None,
                year=new_year or None,
                clean_name=new_title or None,
                local_poster_path=local_poster,
                season=context.get("task_season") if media_type == "tv" else None,
                episode=context.get("task_episode") if media_type == "tv" else None,
            )

        try:
            _cleanup_empty_dirs(old_parent, Path(library_root))
        except OSError as e:
            logger.warning(f"[CLEANUP] 目录清理被跳过（可能由并发竞争引起）: {e}")

        return {"success": True, "rebuilt": rebuilt, "message": message}

