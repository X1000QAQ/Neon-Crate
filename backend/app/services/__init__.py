"""
业务逻辑层 - Services

模块说明：
- scraper: 扫描引擎（并发扫描、正则清洗、物理过滤）
- organizer: 归档器（智能链接引擎）
- subtitle: 字幕引擎（简体优先评分系统）
- metadata: 元数据适配器（TMDB）
"""
from .scraper import ScanEngine, MediaCleaner, MediaFilter
from .organizer import SmartLink
from .subtitle import SubtitleEngine
from .metadata import TMDBAdapter

__all__ = [
    # 扫描引擎
    "ScanEngine",
    "MediaCleaner",
    "MediaFilter",
    
    # 归档器
    "SmartLink",
    
    # 字幕引擎
    "SubtitleEngine",
    
    # 元数据适配器
    "TMDBAdapter",
]
