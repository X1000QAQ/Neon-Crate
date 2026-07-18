"""
归档器服务包入口。

导出：
- `SmartLink`：硬链接优先、软链接兜底的媒体文件链接工具。

说明：本包只提供归档链接能力，不执行扫描、刮削或元数据写入。
"""
from .hardlinker import SmartLink

__all__ = ["SmartLink"]
