"""
_shared.py - tasks 路由包共享状态与统计工具。

职责：
- 保存扫描、刮削、字幕三类后台任务的内存运行态，供状态接口和按钮禁用逻辑读取。
- 提供 `_update_library_counts()`，在任务完成或路径配置变更后刷新仪表盘媒体库计数缓存。
- 将跨子模块共享的状态集中放置，避免 `scan_task`、`scrape_task`、`subtitle_task` 之间互相导入形成循环依赖。

状态边界：
- 这些状态是进程内内存态，服务重启后会重置。
- 真实任务数据仍以数据库和媒体库文件系统为准。
- 本模块只做统计缓存更新，不参与文件名语义识别或物理正则清洗。
"""
import os
import logging
from app.infra.database import get_db_manager
from app.infra.constants import VIDEO_EXTS

logger = logging.getLogger(__name__)

# ==========================================
# 全局任务状态字典
# ==========================================

scan_status = {
    "is_running": False,
    "last_scan_time": None,
    "last_scan_count": 0,
    "error": None
}

scrape_all_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}

find_subtitles_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}


# ==========================================
# 工具函数
# ==========================================

def _update_library_counts():
    """
    盘点媒体库文件数量并写入配置缓存。

    调用时机：
    - 扫描任务完成后。
    - 刮削 / 归档任务完成后。
    - 设置页保存媒体库路径后。

    统计策略：
    - 电影库：统计媒体库根目录下一层文件夹数量。
    - 剧集库：递归统计视频文件数量，每个视频文件视为一集。

    缓存字段：
    - `library_movies_count`：电影数量。
    - `library_tv_count`：剧集集数。

    说明：
    - 这是为了避免 `/system/stats` 每次请求都实时扫盘。
    - 扩展名白名单来自固定常量 `VIDEO_EXTS`，不是用户自定义文件名清洗正则。
    """
    try:
        db = get_db_manager()
        movie_count, tv_count = 0, 0
        paths = db.get_all_config().get("paths", [])
        for p in paths:
            if not p.get("enabled"):
                continue
            folder = p.get("path", "")
            category = p.get("category", "").lower()
            p_type = p.get("type", "").lower()
            if p_type not in ("library", "media") or not folder or not os.path.exists(folder):
                continue
            if category == "movie":
                items = [n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))]
                movie_count += len(items)
            elif category == "tv":
                for root, dirs, files in os.walk(folder):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                            tv_count += 1
        db.set_config("library_movies_count", movie_count)
        db.set_config("library_tv_count", tv_count)
        logger.info(f"[ORG] 媒体库盘点完成: 电影 {movie_count} 部, 剧集 {tv_count} 集")
    except Exception as e:
        logger.error(f"[ORG] 媒体库盘点失败: {e}")
