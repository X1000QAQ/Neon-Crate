import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.infra.database import get_db_manager
from app.services.metadata.metadata_manager import MetadataManager
from app.services.rebuilder.engines import AssetPatchEngine, NuclearEngine

logger = logging.getLogger(__name__)
router = APIRouter()


class ManualRebuildRequest(BaseModel):
    task_id: int
    is_archive: bool = True
    tmdb_id: Optional[int] = None
    keyword_hint: Optional[str] = None
    media_type: str = "movie"
    refix_nfo: bool = True
    refix_poster: bool = True
    refix_subtitle: bool = True
    nuclear_reset: bool = False
    season: Optional[int] = None
    episode: Optional[int] = None
    scope: str = "episode"


@router.post("/manual_rebuild")
async def manual_rebuild(body: ManualRebuildRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    db = get_db_manager()

    # 读取任务记录
    records = db.get_archived_data() if body.is_archive else db.get_all_data(include_ignored=True)
    task_record = next((r for r in records if r["id"] == body.task_id), None)
    if not task_record:
        raise HTTPException(status_code=404, detail=f"任务不存在（task_id={body.task_id}, is_archive={body.is_archive}）")

    target_path: str = task_record.get("target_path") or task_record.get("path") or ""
    if not target_path:
        raise HTTPException(status_code=400, detail="任务缺少 target_path")

    metadata_dir = os.path.dirname(os.path.abspath(target_path))
    if re.match(r"^(Season|S)\s*\d+$|^Specials$", os.path.basename(metadata_dir), re.IGNORECASE):
        metadata_dir = os.path.dirname(metadata_dir)

    # library_root（安全边界）
    try:
        library_root = db.get_active_library_path(body.media_type)
    except Exception:
        library_root = metadata_dir

    tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
    if not tmdb_api_key:
        raise HTTPException(status_code=500, detail="未配置 TMDB API Key")

    # 解析 TMDB 元信息（最小化：优先 body.tmdb_id，其次 DB；不做复杂搜索）
    new_tmdb_id: Optional[int] = body.tmdb_id
    if not new_tmdb_id:
        _db_tmdb = task_record.get("tmdb_id")
        if _db_tmdb:
            try:
                new_tmdb_id = int(_db_tmdb)
            except (ValueError, TypeError):
                new_tmdb_id = None

    new_title: str = task_record.get("title") or ""
    new_year: str = str(task_record.get("year") or "")
    new_imdb_id: str = task_record.get("imdb_id") or ""

    # TV season/episode：仅允许 episode scope 覆盖
    if body.scope == "episode":
        task_season = body.season if body.season is not None else task_record.get("season")
        task_episode = body.episode if body.episode is not None else task_record.get("episode")
    else:
        task_season = task_record.get("season")
        task_episode = task_record.get("episode")

    # 若有 tmdb_id，拉详情补齐 title/year/imdb
    if new_tmdb_id:
        from app.services.metadata.adapters import TMDBAdapter

        rename_lang = db.get_config("rename_lang", "zh")
        poster_lang = db.get_config("poster_lang", "zh")
        scraper = TMDBAdapter(api_key=tmdb_api_key, rename_lang=rename_lang, poster_lang=poster_lang)
        try:
            detail = (
                scraper.get_tv_details(str(new_tmdb_id))
                if body.media_type == "tv"
                else scraper.get_movie_details(str(new_tmdb_id))
            )
            if detail:
                new_title = detail.get("title") or detail.get("name") or new_title
                release = detail.get("release_date") or detail.get("first_air_date") or ""
                new_year = release[:4] if release else new_year
                new_imdb_id = (detail.get("external_ids") or {}).get("imdb_id") or new_imdb_id
        except Exception:
            pass

    # ── TV library_root 智能纠偏（白名单安全锁，防止 download 目录污染）────
    # 推算出的根目录必须在已配置的合法媒体库白名单内，绝不能是 download 目录
    if body.media_type == "tv" and target_path:
        try:
            _p = Path(target_path)
            _deduced_root: Optional[str] = None

            if _p.parent.name.lower().startswith("season"):
                # 文件在标准 Season 子目录下：Season → 剧集根 → 媒体库根
                _deduced_root = str(_p.parent.parent.parent)
            else:
                # 文件不在标准 Season 目录（如仍在 download）：向同剧已入库兄弟集借用坐标
                if new_imdb_id:
                    from app.services.rebuilder.rebuild_utils import _get_sibling_episodes as _gse
                    _sibs = _gse(db, new_imdb_id, season=None, scope="series")
                    for _sib in _sibs:
                        _sib_p = Path(_sib.get("target_path") or _sib.get("path") or "")
                        if _sib_p.exists() and _sib_p.parent.name.lower().startswith("season"):
                            _deduced_root = str(_sib_p.parent.parent.parent)
                            break

            # 安全锁：推算出的根目录必须在配置的合法 TV 媒体库白名单内
            if _deduced_root:
                try:
                    _all_cfg = db.get_all_config()
                    _valid_libs = [
                        cp["path"] for cp in (_all_cfg.get("paths") or [])
                        if cp.get("type") == "library" and cp.get("media_type") == "tv"
                           and cp.get("enabled", True)
                    ]
                except Exception:
                    _valid_libs = []
                if _valid_libs:
                    if _deduced_root in _valid_libs:
                        library_root = _deduced_root
                        logger.info(f"[REBUILD] TV library_root 白名单命中: {library_root}")
                    else:
                        logger.warning(
                            f"[REBUILD] TV library_root 推算结果 '{_deduced_root}' "
                            f"不在白名单 {_valid_libs}，保留配置值: {library_root}"
                        )
                else:
                    # 无白名单配置时，保守使用推算值（兼容未配置 paths 的旧环境）
                    library_root = _deduced_root
                    logger.info(f"[REBUILD] TV library_root 推算（无白名单）: {library_root}")
        except Exception as _lr_err:
            logger.warning(f"[REBUILD] TV library_root 推算失败（使用默认值）: {_lr_err}")

    meta_manager = MetadataManager(tmdb_api_key=tmdb_api_key)

    ctx = {
        "media_type": body.media_type,
        "scope": body.scope,
        "new_tmdb_id": new_tmdb_id,
        "new_imdb_id": new_imdb_id,
        "new_title": new_title,
        "new_year": new_year,
        "metadata_dir": metadata_dir,
        "library_root": library_root,
        "target_path": target_path,
        "task_season": task_season,
        "task_episode": task_episode,
        "is_archive": body.is_archive,
    }

    if body.nuclear_reset:
        return NuclearEngine(db, meta_manager, background_tasks).execute(task_record, body, ctx)
    return AssetPatchEngine(db, meta_manager, background_tasks).execute(task_record, body, ctx)


@router.get("/search_tmdb")
async def search_tmdb(
    keyword: str,
    media_type: str = "movie",
) -> list:
    """
    TMDB 关键词搜索（用于手动补录弹窗的候选选择，返回 Top 10）。

    业务链路：
    校验 TMDB API Key → 调用 TMDBAdapter.search_media → 返回候选列表。

    Args:
        keyword:    搜索关键词（Query 参数）。
        media_type: 媒体类型（Query 参数，movie/tv）。

    Returns:
        list[dict]: 候选列表（最多 10 条），字段包含 tmdb_id/title/year/overview/poster_path。

    Raises:
        HTTPException:
            - 500: 未配置 TMDB API Key。
            - 502: TMDB 请求失败（上游不可用/响应异常）。
    """
    db = get_db_manager()
    tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
    if not tmdb_api_key:
        raise HTTPException(status_code=500, detail="未配置 TMDB API Key")

    rename_lang = db.get_config("rename_lang", "zh")
    poster_lang = db.get_config("poster_lang", "zh")

    from app.services.metadata.adapters import TMDBAdapter
    scraper = TMDBAdapter(api_key=tmdb_api_key, rename_lang=rename_lang, poster_lang=poster_lang)

    try:
        results = scraper.search_media(keyword, media_type=media_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TMDB 搜索失败: {e}")

    normalized = []
    for r in results[:10]:
        tmdb_id = r.get("tmdb_id") or r.get("id")
        title   = r.get("title") or r.get("name") or ""
        date_str = r.get("release_date") or r.get("first_air_date") or ""
        year    = date_str[:4] if date_str else ""
        normalized.append({
            "tmdb_id":    tmdb_id,
            "title":      title,
            "year":       year,
            "overview":   r.get("overview", ""),
            "poster_path": r.get("poster_path", ""),
            "imdb_id":    r.get("imdb_id", ""),
        })

    return normalized

