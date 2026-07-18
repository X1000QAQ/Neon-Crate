"""
tasks 路由包入口。

职责：
- 对外导出统一的 `router`，供 API v1 聚合器挂载到 `/tasks` 前缀。
- 继续导出扫描、刮削、字幕后台任务函数，保持 `lifespan`、AI Agent 和定时巡逻链路的历史 import 路径兼容。

维护提示：
- 这里是兼容导出层，不承载业务逻辑。
- 移除导出项前必须检查后台任务、巡逻任务和 Agent 口令即执行链路。
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
