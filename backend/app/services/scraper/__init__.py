"""
刮削 / 扫描服务包入口。

导出：
- `ScanEngine`：并发文件发现和上下文采集。
- `MediaCleaner`：结构化文件名工具和归档路径安全化。
- `MediaFilter`：基础物理过滤器。

边界：
- 本包不负责 LLM 意图识别，也不直接写 NFO / 海报。
- 元数据搜索和写盘分别由 `metadata` 服务和任务路由链路调用。
"""
from .engine import ScanEngine
from .cleaner import MediaCleaner
from .filters import MediaFilter

__all__ = ["ScanEngine", "MediaCleaner", "MediaFilter"]
