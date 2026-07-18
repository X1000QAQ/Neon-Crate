"""
重构工具函数 - 路径计算、字幕探测、目录清理和视频定位。

职责：
- 为 `NuclearEngine` 和 `AssetPatchEngine` 提供可复用的文件系统辅助能力。
- 计算 TV 单集标准目标路径。
- 查询同剧 / 同季任务记录，支持批量重构。
- 以物理目录为准扫描兄弟集，减少数据库错乱对核级重构的影响。
- 在安全边界内清理元数据文件和空目录。

安全边界：
- 核级清理必须校验 `metadata_dir` 位于 `library_root` 内。
- `library_root` 过浅时拒绝操作，防止误删根目录或挂载根。
- 删除文件前会二次解析路径，防止软链接穿越。
"""
import glob
import logging
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from app.infra.constants import VIDEO_EXTS_EXTENDED

logger = logging.getLogger(__name__)


def _check_local_subtitles(video_path: str, sub_exts: frozenset = None) -> bool:
    """
    检查视频同级目录下是否存在可复用字幕。

    匹配顺序：
    1. 严格匹配：`视频名 + 字幕扩展名`。
    2. 通配匹配：`视频名.*.字幕扩展名`，兼容多语言后缀。
    3. 模糊匹配：
       - 剧集：字幕名包含同一 `SxxExx`。
       - 电影：字幕名与视频名存在包含关系。

    Returns:
        bool: True 表示已有字幕，可跳过下载。
    """
    if not video_path or not os.path.exists(video_path):
        return False
    dir_name = os.path.dirname(video_path)
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    valid_exts = sub_exts if sub_exts else frozenset({".srt", ".ass", ".vtt", ".sub", ".idx"})

    # 1. 严格与通配匹配 (原有逻辑)
    for ext in valid_exts:
        if os.path.exists(os.path.join(dir_name, f"{base_name}{ext}")):
            return True
        if glob.glob(os.path.join(glob.escape(dir_name), f"{glob.escape(base_name)}.*{ext}")):
            return True

    # 2. 终极模糊匹配（只要有字幕文件就算过）
    try:
        episode_match = re.search(r"(S\d+E\d+)", base_name, re.IGNORECASE)
        for file in os.listdir(dir_name):
            if os.path.splitext(file)[1].lower() in valid_exts:
                if episode_match:
                    # 剧集：只要字幕名包含同样的季集号 (如 S01E01) 就放行
                    if episode_match.group(1).lower() in file.lower():
                        return True
                else:
                    # 电影模式：要求字幕文件名（去除后缀）与视频文件名存在包含关系，防止误判遗留字幕
                    sub_base = os.path.splitext(file)[0].lower()
                    vid_base = base_name.lower()
                    if sub_base in vid_base or vid_base in sub_base:
                        return True
    except Exception as e:
        logger.debug(f"[SUBTITLE] 模糊匹配检测出现异常 (可忽略): {e}")
    return False


def _nuclear_clean_directory(
    metadata_dir: str, library_root: str, video_exts: frozenset = None, protect_metadata: bool = False
) -> dict:
    """
    核级清理：删除 metadata_dir 下除视频本体以外的所有文件。

    安全保险栓：
    1. metadata_dir 必须是 library_root 的子路径（防越权）
    2. library_root 不得为根目录或常见危险路径（防止误删 /storage 根目录）
    3. 每个文件二次校验在 metadata_dir 内（防软链穿越）
    4. 只操作 metadata_dir 本层文件，不递归子目录
    5. video_exts 白名单内的文件绝对保留
    """
    _video_exts = video_exts if video_exts else VIDEO_EXTS_EXTENDED

    resolved_meta = Path(metadata_dir).resolve()
    resolved_lib = Path(library_root).resolve()

    # 保险栓 1：library_root 不得为危险路径（深度 < 2 的路径视为危险）
    if len(resolved_lib.parts) < 3:
        raise PermissionError(f"[NUCLEAR SAFELOCK] library_root 路径过浅，拒绝操作: {library_root}")

    # 保险栓 2：metadata_dir 必须是 library_root 的子路径
    try:
        resolved_meta.relative_to(resolved_lib)
    except ValueError:
        raise PermissionError(
            f"[NUCLEAR SAFELOCK] metadata_dir '{metadata_dir}' 不在 library_root '{library_root}' 内，拒绝清理"
        )

    deleted, kept_videos = [], []
    _protected_names = {
        "tvshow.nfo",
        "movie.nfo",
        "poster.jpg",
        "poster.png",
        "poster.webp",
        "fanart.jpg",
        "fanart.png",
        "fanart.webp",
    }
    for f in resolved_meta.iterdir():
        if not f.is_file():
            continue  # 跳过子目录
        # 保险栓 3：防软链穿越
        try:
            f.resolve().relative_to(resolved_meta)
        except ValueError:
            logger.warning(f"[NUCLEAR SAFELOCK] 跳过越界文件: {f}")
            continue
        if f.suffix.lower() in _video_exts:
            kept_videos.append(str(f))
            logger.info(f"[NUCLEAR] 保留视频本体: {f.name}")
        elif protect_metadata and f.name.lower() in _protected_names:
            logger.info(f"[NUCLEAR] 金标准护盾生效，保留元数据: {f.name}")
            continue
        else:
            f.unlink()
            deleted.append(str(f))
            logger.info(f"[NUCLEAR] 已删除: {f.name}")

    logger.info(f"[NUCLEAR] 清理完成: 删除 {len(deleted)} 个文件，保留视频 {len(kept_videos)} 个")
    return {"deleted": deleted, "kept_videos": kept_videos}


def _get_sibling_episodes(db, imdb_id: str, season: Optional[int], scope: str) -> list:
    """
    从双表查询同组集数记录（三级装甲补录协议辅助函数）。

    Args:
        db:      DatabaseManager 实例
        imdb_id: 剧集 IMDb ID（跨表唯一键）
        season:  季号（scope="season" 时用于过滤，"series" 时忽略）
        scope:   "series" 返回该剧所有集；"season" 返回指定季所有集

    Returns:
        list[dict]: 符合条件的任务记录列表，每条含 id/is_archive/target_path/season/episode
    """
    if not imdb_id:
        return []
    try:
        all_hot = db.get_all_data(include_ignored=False)
        all_cold = db.get_archived_data()
        # 冷表覆盖热表（以 id 为键合并，已归档状态优先）
        combined: dict = {r["id"]: r for r in all_hot}
        for r in all_cold:
            combined[r["id"]] = r

        results = [
            r
            for r in combined.values()
            if r.get("imdb_id") == imdb_id
            and (r.get("type") == "tv" or not r.get("type"))  # 兼容无 type 字段的旧记录
            and (r.get("target_path") or r.get("path"))       # 接受 path（下载目录中未归档的集数）
        ]
        if scope == "season" and season is not None:
            results = [r for r in results if r.get("season") == season]
        return results
    except Exception as e:
        logger.warning(f"[REBUILD] _get_sibling_episodes 查询异常: {e}")
        return []


def _calc_tv_target_path(
    library_root: str, new_title: str, new_year: str, season: int, episode: int, ext: str
) -> str:
    """
    计算 TV 单集的标准目标绝对路径。
    格式：{library_root}/{Title} ({Year})/Season {S}/{Title} ({Year}) - S{S}E{E}.ext
    """
    safe_title = re.sub(r"[\\/:*?\"<>|]", "_", new_title.strip())
    year_str = f" ({new_year})" if new_year else ""
    show_dir = f"{safe_title}{year_str}"
    season_dir = f"Season {season}"
    ep_name = f"{safe_title}{year_str} - S{season:02d}E{episode:02d}{ext}"
    return os.path.join(library_root, show_dir, season_dir, ep_name)


def _cleanup_empty_dirs(start: Path, stop_at: Path) -> None:
    """
    从 start 目录向上递归删除空目录，直到 stop_at（stop_at 本身不删除）。
    用于全量重建（Nuclear）尾相之后，清理已无内容的剧集或季目录壳层。
    """
    current = start.resolve()
    stop_at = stop_at.resolve()
    while current != stop_at and current != current.parent:
        try:
            if current.exists() and not any(current.iterdir()):
                current.rmdir()
                logger.info(f"[NUCLEAR] 清理空目录: {current}")
                current = current.parent
            else:
                break
        except OSError as _ce:
            logger.warning(f"[NUCLEAR] 清理空目录失败（不阻断）: {_ce}")
            break


def _locate_video_for_task(task_record: dict, db_video_exts: frozenset, search_dir: Optional[str] = None) -> Optional[str]:
    """
    四级精准定位当前任务对应的视频文件。
    
    职责边界：
    - 本函数只负责"定位文件"，不判断文件来源（下载源 vs 媒体库）
    - 调用方（如 Nuclear 引擎）需通过 is_in_library 判断来决定后续处理方式
    - Level A 可能返回下载源路径，这是预期行为
    
    Level A: target_path / path 直接存在
    Level B: inode 追踪（硬链接场景，在 search_dir 内匹配）
    Level C: file_name 精确匹配（在 search_dir 内查找）
    Level D: 三级失败 → 返回 None（由调用方决定是熔断还是跳过）
    """
    _source_path = task_record.get("target_path") or task_record.get("path") or ""

    # Level A
    if _source_path and Path(_source_path).exists() and Path(_source_path).suffix.lower() in db_video_exts:
        logger.info(f"[NUCLEAR] 精准定位视频（source_path 直接命中）: {_source_path}")
        return _source_path

    if search_dir:
        _sdir = Path(search_dir)

        # Level B: inode 追踪
        if _source_path and Path(_source_path).exists():
            try:
                src_inode = os.stat(_source_path).st_ino
                for f in _sdir.rglob("*"):
                    if f.is_file() and f.suffix.lower() in db_video_exts:
                        if os.stat(f).st_ino == src_inode:
                            logger.info(f"[NUCLEAR] 精准定位视频（inode 匹配）: {f}")
                            return str(f)
            except OSError:
                pass

        # Level C: file_name 精确匹配
        _task_fname = task_record.get("file_name") or ""
        if _task_fname:
            for f in _sdir.rglob("*"):
                if f.is_file() and f.name == _task_fname and f.suffix.lower() in db_video_exts:
                    logger.info(f"[NUCLEAR] 精准定位视频（file_name 匹配）: {f}")
                    return str(f)

    logger.warning(f"[NUCLEAR] 无法定位视频: id={task_record.get('id')}, " f"source='{_source_path}'")
    return None


def _get_physical_siblings(show_root: str, season: Optional[int], video_exts: frozenset) -> list:
    """
    从物理目录直接扫描剧集文件并提取季集坐标。

    用途：
    - 核级重构时以磁盘现状为准，降低数据库记录错乱的影响。
    - `season=None` 表示扫描整剧；指定 season 时只返回该季。

    Returns:
        list[dict]: 每项包含 `path`、`season`、`episode`。
    """
    results = []
    s_root = Path(show_root)
    if not s_root.exists():
        return results
    se_pattern = re.compile(r"S(\d+)E(\d+)", re.IGNORECASE)
    for f in s_root.rglob("*"):
        if f.is_file() and f.suffix.lower() in video_exts:
            match = se_pattern.search(f.name)
            if match:
                ep_s, ep_e = int(match.group(1)), int(match.group(2))
                if season is None or ep_s == season:
                    results.append({"path": str(f), "season": ep_s, "episode": ep_e})
    return results

