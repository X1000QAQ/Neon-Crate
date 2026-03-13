"""
tasks 包 - 任务管理端点（拆分自原 tasks.py）

向后兼容导出层：保持所有外部 import 路径不变。
外部调用方（lifespan.py / agent.py / cron_loop 等）无需修改任何 import。
"""
from .scan_task import perform_scan_task_sync
from .scrape_task import perform_scrape_all_task_sync, scrape_all_status
from .subtitle_task import perform_find_subtitles_task_sync, find_subtitles_status
from .router import router

__all__ = [
    "router",
    "perform_scan_task_sync",
    "perform_scrape_all_task_sync",
    "scrape_all_status",
    "perform_find_subtitles_task_sync",
    "find_subtitles_status",
]
