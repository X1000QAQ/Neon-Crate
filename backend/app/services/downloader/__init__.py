"""
下载器服务包入口。

导出：
- `ServarrClient`：Radarr / Sonarr 下载任务分发客户端。

边界：
- 本包不做 AI 意图识别，不直接接收用户输入。
- 下载执行应由授权确认链路调用。
"""

from .servarr import ServarrClient

__all__ = ["ServarrClient"]
