"""
字幕服务包入口。

导出：
- `SubtitleEngine`：OpenSubtitles 检索、评分、下载和状态回写引擎。

说明：
- 全量任务编排、并发锁和任务间休眠由 API 路由任务模块负责。
"""
from .engine import SubtitleEngine

__all__ = ["SubtitleEngine"]
