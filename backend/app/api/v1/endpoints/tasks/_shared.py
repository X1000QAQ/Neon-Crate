"""
_shared.py - tasks 包共享状态与工具函数

包含：
1. 全局任务状态字典（scan_status / scrape_all_status / find_subtitles_status）
2. _update_library_counts() — 物理扫盘统计工具函数

所有其他子模块从此处导入共享状态，避免循环依赖。
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
    物理扫盘统计媒体库数量，写入数据库缓存
    
    设计目标：
    - 提供准确的媒体库统计数据
    - 避免在 /stats 接口实时扫盘（性能问题）
    - 由扫描/刮削任务完成后调用，异步更新
    
    统计策略：
    
    电影统计：
    - 统计媒体库第一层子文件夹数
    - 每个文件夹 = 一部电影
    - 例如：/media/movies/The Matrix (1999)/ 算 1 部电影
    
    剧集统计：
    - 递归统计所有视频文件数
    - 每个文件 = 一集
    - 例如：/media/tv/Breaking Bad (2008)/Season 1/S01E01.mkv 算 1 集
    
    支持的视频格式：
    - .mkv、.mp4、.avi、.mov、.wmv、.ts、.flv、.m2ts
    
    调用时机：
    - 扫描任务完成后
    - 刮削任务完成后
    - 配置保存后（用户修改媒体库路径）
    
    缓存位置：
    - library_movies_count：电影数量
    - library_tv_count：剧集数量
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
