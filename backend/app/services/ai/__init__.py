"""
AI 引擎模块 - 智能对话与意图识别

功能：
1. 自然语言对话处理
2. 意图识别与指令路由
3. 系统状态查询与反馈
4. 双引擎 LLM 支持（云端 API / 本地 Ollama）
5. 智能媒体名称清洗与搜索优化
"""

from .agent import AIAgent
from .llm_client import LLMClient

__all__ = ["AIAgent", "LLMClient"]
