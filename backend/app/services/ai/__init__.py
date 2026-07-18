"""
AI 服务包入口。

导出：
- `AIAgent`：对话编排、意图识别和下载候选授权缓存。
- `LLMClient`：云端 / 本地模型统一调用和降级调度。

边界：
- 本包只负责 AI 决策与模型通信。
- 后台任务执行、Servarr 下载、文件归档和元数据写盘均由路由层或其他服务层模块完成。
"""

from .agent import AIAgent
from .llm_client import LLMClient

__all__ = ["AIAgent", "LLMClient"]
