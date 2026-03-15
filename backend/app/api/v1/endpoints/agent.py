"""
AI 对话端点 - Agent API

提供 AI 助手的对话能力，支持：
1. 自然语言交互
2. 意图识别与指令下发
3. 系统状态查询

AI 控制链路架构：
- 协议约束层：llm_client.py force_json + AIIntentModel Pydantic 校验
- 意图审计层：AIActionEnum 白名单 + Dispatcher 频率管控
- 口令即执行：SCAN/SCRAPE/SUBTITLE 意图在 /chat 端点直接分发后台任务
- 授权决策层：DOWNLOAD 意图返回 PendingActionPayload，前端渲染全屏确认界面

执行状态管控原则：
- check_cooldown() 为只读预检，不写入时间戳
- record_execution() 为唯一的冷却时间戳写入入口，在任务成功分发后调用
"""
import asyncio
import logging
from fastapi import APIRouter, BackgroundTasks

from app.infra.database import get_db_manager
from app.models.domain_system import (
    ChatRequest, ChatResponse, PendingActionPayload, CandidateItem
)
from app.services.ai import AIAgent
from app.services.ai.dispatcher import Dispatcher, AIActionEnum

router = APIRouter()
logger = logging.getLogger(__name__)

# 模块级单例：保证 _pending_candidates 等对话状态跨请求存活
_agent_instance: AIAgent | None = None

def _get_agent() -> AIAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AIAgent(get_db_manager())
    return _agent_instance


# ── 口令即执行意图表：识别后在 /chat 端点直接分发后台任务 ──────────────
_DIRECT_ACTIONS = {
    AIActionEnum.ACTION_SCAN:     "全盘扫描",
    AIActionEnum.ACTION_SCRAPE:   "全量刮削",
    AIActionEnum.ACTION_SUBTITLE: "字幕补全",
}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    AI 对话接口（口令即执行 + 授权决策分流）

    执行链路：
    1. 意图识别：agent.process_message 解析自然语言，返回意图代码
    2. 白名单校验：AIActionEnum 过滤非法意图
    3. 分流路由：
       - SCAN/SCRAPE/SUBTITLE：频率预检 → 直接分发 BackgroundTasks → record_execution
       - DOWNLOAD：构造 PendingActionPayload（含 TMDB 元数据）→ 返回前端触发全屏确认
       - CHAT/LOCAL_SEARCH/SYSTEM_STATUS：直接返回文本

    Args:
        request: 包含用户消息的请求体
        background_tasks: FastAPI 后台任务管理器

    Returns:
        ChatResponse: AI 回复文本、意图代码与可选的下载确认载荷
    """
    try:
        agent = _get_agent()
        result = await agent.process_message(request.message)

        # ── V2.0 血缘溯源：从 LLM 客户端读取本次调用的引擎信息 ────────────
        _ei = getattr(agent.llm_client, 'last_engine_info', {})
        _provider  = _ei.get('provider', '')
        _fallback  = _ei.get('fallback', False)
        if _provider == 'local' and _fallback:
            engine_tag = 'local->cloud'
        elif _provider:
            engine_tag = _provider
        else:
            engine_tag = None

        # 兼容三元组（携带结构化候选列表）和二元组
        if isinstance(result, tuple) and len(result) == 3:
            response_text, action_code, candidates_raw = result
        else:
            response_text, action_code = result
            candidates_raw = []

        # 构造结构化候选列表
        candidates_out: list[CandidateItem] = []
        if candidates_raw:
            for c in candidates_raw:
                candidates_out.append(CandidateItem(
                    title=c.get("title", ""),
                    year=str(c.get("year", "")),
                    media_type=c.get("media_type", "movie"),
                    tmdb_id=c.get("id") or c.get("tmdb_id"),
                ))

        # ── 意图审计层：白名单过滤非法意图代码 ──────────────────────────────
        if not action_code:
            return ChatResponse(response=response_text, action=None, candidates=candidates_out, engine_tag=engine_tag)

        try:
            validated_action = AIActionEnum(action_code)
        except ValueError:
            logger.warning(f"[AI-AUDIT] ⛔ 非法 action_code 已过滤: {repr(action_code)}")
            return ChatResponse(response=response_text, action=None, candidates=candidates_out, engine_tag=engine_tag)

        # ── 口令即执行：SCAN/SCRAPE/SUBTITLE 直接分发后台任务 ────────────────
        if validated_action in _DIRECT_ACTIONS:
            is_cooling, remaining = Dispatcher.check_cooldown(validated_action)
            if is_cooling:
                logger.warning(f"[AI-AUDIT] {action_code} 频率限制中，剩余 {remaining}s")
                return ChatResponse(
                    response=response_text + f"\n\n⚠️ 操作频率受限，神经链路冷却中（剩余 {remaining}s），请稍后重试。",
                    action=None
                )
            try:
                from app.api.v1.endpoints.tasks.scan_task import perform_scan_task_sync
                from app.api.v1.endpoints.tasks.scrape_task import perform_scrape_all_task_sync
                from app.api.v1.endpoints.tasks.subtitle_task import perform_find_subtitles_task_sync

                label = _DIRECT_ACTIONS[validated_action]
                if validated_action == AIActionEnum.ACTION_SCAN:
                    background_tasks.add_task(perform_scan_task_sync)
                    reply = f"✅ {label}指令已透传，物理扫描任务已启动。"
                elif validated_action == AIActionEnum.ACTION_SCRAPE:
                    background_tasks.add_task(perform_scrape_all_task_sync)
                    reply = f"✅ {label}指令已下达，元数据更新流程已启动。"
                elif validated_action == AIActionEnum.ACTION_SUBTITLE:
                    background_tasks.add_task(perform_find_subtitles_task_sync)
                    reply = f"✅ {label}指令已执行，检索任务已进入队列。"
                else:
                    reply = response_text

                # 状态持久化：仅在后台任务成功分发后更新频率限制时间戳
                Dispatcher.record_execution(validated_action)
                logger.info(f"[AI-EXEC] ✅ {label} 已分发，冷却计时开始")
                return ChatResponse(response=reply, action=action_code)

            except Exception as e:
                logger.error(f"[AI-EXEC] 任务分发异常: {e}", exc_info=True)
                return ChatResponse(response=f"任务启动失败：{str(e)}", action=None)

        # ── 授权决策层：DOWNLOAD 意图构造元数据载荷，返回前端触发全屏确认 ─────
        if validated_action == AIActionEnum.DOWNLOAD:
            # 从 agent 内部状态中提取本次 DOWNLOAD 意图的 TMDB 元数据
            # agent.process_message 在处理 DOWNLOAD 时会将候选结果写入 _last_download_meta
            # 持久化恢复：优先从内存读取，若为空则尝试从数据库恢复（应对进程重启场景）
            meta = getattr(agent, '_last_download_meta', None)
            if not meta:
                import json
                db = get_db_manager()
                meta_raw = db.get_config("_pending_download_meta", "")
                if meta_raw:
                    try:
                        meta = json.loads(meta_raw)
                        logger.info("[AI-DOWNLOAD] 从数据库恢复下载元数据")
                    except Exception as e:
                        logger.warning(f"[AI-DOWNLOAD] 元数据恢复失败: {e}")
                        meta = {}
                else:
                    meta = {}

            # Fallback 保护：若元数据完全缺失，返回友好错误提示
            if not meta or (not meta.get('title') and not meta.get('clean_name')):
                logger.warning("[AI-DOWNLOAD] 元数据缺失，无法构造确认载荷")
                return ChatResponse(
                    response="下载元数据已过期或丢失，请重新发起下载请求。",
                    action=None
                )

            pending = PendingActionPayload(
                action=action_code,
                label="下载",
                description=f"将「{meta.get('title', meta.get('clean_name', '未知'))}」加入下载队列",
                title=meta.get('title'),
                year=str(meta.get('year', '')) if meta.get('year') else None,
                poster_url=meta.get('poster_url'),
                overview=meta.get('overview'),
                media_type=meta.get('media_type', 'movie'),
                tmdb_id=meta.get('tmdb_id'),
                clean_name=meta.get('clean_name'),
                en_name=meta.get('en_name'),
                is_duplicate=meta.get('is_duplicate', False),
                existing_status=meta.get('existing_status'),
            )
            logger.info(f"[AI-DOWNLOAD] ⏸️  下载确认载荷已构造: {meta.get('title')}")
            return ChatResponse(
                response=response_text,
                action=action_code,
                pending_action=pending,
            )

        return ChatResponse(response=response_text, action=action_code, engine_tag=engine_tag)

    except asyncio.CancelledError:
        # 🚀 异步链路治理 — 步骤 3：后端资源回收
        # 触发来源：前端 AiSidebar 调用 abortControllerRef.current.abort()，
        # 浏览器物理切断网络连接，Uvicorn 在下一个 await 点感知到后注入 CancelledError。
        # 必须 re-raise：让 ASGI 框架安全清理连接状态，不能吞掉此异常。
        logger.info("📡 [Agent] 前端 AbortController 触发中止，LLM 推理已终止，资源已释放。")
        raise
    except Exception as e:
        logger.error(f"❌ [Agent] 交互异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/confirm", response_model=ChatResponse)
async def confirm_action(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    授权决策端点：用户在全屏确认界面点击「授权下载」后调用

    request.message 格式为 JSON 字符串，携带完整的 PendingActionPayload 字段，
    端点解析后调用 ServarrClient 执行真正的下载请求。

    Args:
        request: message 字段为 JSON 序列化的确认载荷
        background_tasks: FastAPI 后台任务管理器（预留）

    Returns:
        ChatResponse: 执行结果文本
    """
    import json
    try:
        payload = json.loads(request.message)
    except Exception:
        # 兼容旧格式：message 直接为 action_code 字符串
        payload = {"action": request.message.strip()}

    action_code = payload.get("action", "").strip()

    try:
        validated_action = AIActionEnum(action_code)
    except ValueError:
        logger.warning(f"[AI-CONFIRM] ⛔ 非法 action_code: {repr(action_code)}")
        return ChatResponse(response="无效的指令代码，授权已拒绝。", action=None)

    # ── 下载授权执行 ───────────────────────────────────────────────────
    if validated_action == AIActionEnum.DOWNLOAD:
        try:
            from app.services.downloader import ServarrClient
            db = get_db_manager()
            servarr = ServarrClient(db)

            # 从载荷中恢复下载参数
            en_name    = payload.get("en_name", "")
            clean_name = payload.get("clean_name", "")
            year       = payload.get("year", "")
            media_type = payload.get("media_type", "movie")
            tmdb_id    = payload.get("tmdb_id")  # 候选选择场景下携带精确 TMDB ID
            search_name = en_name if en_name else clean_name

            if not search_name:
                return ChatResponse(response="载荷缺失片名参数，指令执行中止。", action=None)

            if media_type == "tv":
                result = await servarr.add_series(search_name, year, tmdb_id=tmdb_id)
            else:
                result = await servarr.add_movie(search_name, year, tmdb_id=tmdb_id)

            if result["success"]:
                title = result["data"].get("title", clean_name)
                reply = f"✅ 「{title}」已加入下载队列，Radarr/Sonarr 自动抓取流程已启动。"
            elif result.get("data", {}).get("status") == "exists":
                title = result.get("data", {}).get("title", clean_name)
                reply = f"「{title}」已在监控列表中，无需重复添加。"
            else:
                reply = f"下载指令执行失败：{result['msg']}，请检查 Radarr/Sonarr 配置或片名准确性。"

            return ChatResponse(response=reply, action=action_code)

        except Exception as e:
            logger.error(f"[AI-CONFIRM] 下载执行异常: {e}", exc_info=True)
            return ChatResponse(response=f"执行层异常：{str(e)}", action=None)

    return ChatResponse(response="不支持对此指令的授权操作。", action=None)
