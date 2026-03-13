"""
AI 对话端点 - Agent API

提供 AI 助手的对话能力，支持：
1. 自然语言交互
2. 意图识别与指令下发
3. 系统状态查询
"""
import logging
from fastapi import APIRouter, BackgroundTasks

from app.infra.database import get_db_manager
from app.models.domain_system import ChatRequest, ChatResponse
from app.services.ai import AIAgent

router = APIRouter()
logger = logging.getLogger(__name__)

# 模块级单例：保证 _pending_candidates 等对话状态跨请求存活
_agent_instance: AIAgent | None = None

def _get_agent() -> AIAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AIAgent(get_db_manager())
    return _agent_instance


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    AI 对话接口
    
    接收用户消息，返回 AI 响应和可能的意图指令
    
    Args:
        request: 包含用户消息的请求体
        background_tasks: FastAPI 后台任务管理器
        
    Returns:
        ChatResponse: 包含 AI 回复文本和意图代码
    """
    # 获取单例 Agent（保留对话状态）
    agent = _get_agent()
    
    # 🚨 关键修复：必须使用 await 调用协程
    response_text, action_code = await agent.process_message(request.message)
    
    # 🚀 实现自动一致性触发（函数内部导入，避免循环引用）
    if action_code:
        try:
            from app.api.v1.endpoints.tasks.scan_task import perform_scan_task_sync
            from app.api.v1.endpoints.tasks.scrape_task import perform_scrape_all_task_sync
            from app.api.v1.endpoints.tasks.subtitle_task import perform_find_subtitles_task_sync
            
            if action_code == "ACTION_SCAN":
                background_tasks.add_task(perform_scan_task_sync)
                logger.info("[AI-EXEC] 已自动触发物理扫描")
            elif action_code == "ACTION_SCRAPE":
                background_tasks.add_task(perform_scrape_all_task_sync)
                logger.info("[AI-EXEC] 已自动触发全量刮削")
            elif action_code == "ACTION_SUBTITLE":
                background_tasks.add_task(perform_find_subtitles_task_sync)
                logger.info("[AI-EXEC] 已自动触发查找字幕")
            elif action_code == "DOWNLOAD":
                # 🚀 V11 寻猎者计划 - 下载意图已在 agent 内部完成
                # 此处无需额外操作，仅记录日志
                logger.info("[AI-EXEC] 已处理下载请求（寻猎者引擎）")
        except Exception as e:
            logger.error(f"[AI-EXEC] 自动触发任务失败: {e}", exc_info=True)
            # 不中断响应，继续返回 AI 回复
    
    # 组装响应
    return ChatResponse(
        response=response_text,
        action=action_code
    )
