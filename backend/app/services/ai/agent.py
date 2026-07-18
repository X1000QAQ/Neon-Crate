"""
AI Agent 核心模块 - 对话编排、意图识别与授权决策。

职责：
- 接收用户自然语言消息，融合人格设定和总控路由规则后调用 LLM。
- 将 LLM 返回的结构化意图交给 `Dispatcher` 做白名单和参数校验。
- 对扫描、刮削、字幕等低风险动作返回可直接分发的 action code。
- 对下载意图执行 TMDB 候选检索、候选状态持久化和下载确认元数据缓存。

控制边界：
- 本模块只负责“识别与决策”，不直接执行下载，也不直接移动媒体文件。
- 下载必须经 `/confirm` 授权端点调用 Servarr，避免模型输出绕过人工确认。
- 媒体文件名语义识别依赖 LLM 结构化输出，不恢复 RegexLab / DB 正则清洗链路。

容错策略：
- LLM 结构化输出先经 JSON 提取器处理，再经 `Dispatcher` 强校验。
- LLM 调用失败或总控规则为空时，降级到本地关键词规则引擎。
- 用户选择候选时，从数据库读取 `_pending_candidates`，适配开发热重载和多请求场景。
"""
import json
import re
import asyncio
import logging
from typing import Dict, Optional, Tuple
from pathlib import Path

from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class AIAgent:
    """
    AI 智能助手。

    主要职责：
    - 维护对话入口 `process_message()`。
    - 根据 LLM / 规则引擎结果返回自然语言回复和可选 action code。
    - 管理下载候选列表和待授权下载元数据。

    重要约束：
    - action code 只是路由层触发后台任务的信号，不代表任务已经执行完成。
    - DOWNLOAD 意图必须停留在授权决策层，不能在本类中直接调用下载器执行。
    """
    
    # 意图常量定义
    ACTION_SCAN = "ACTION_SCAN"
    ACTION_SCRAPE = "ACTION_SCRAPE"
    ACTION_SUBTITLE = "ACTION_SUBTITLE"
    DOWNLOAD = "DOWNLOAD"
    LOCAL_SEARCH = "LOCAL_SEARCH"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    CHAT = "CHAT"
    
    def __init__(self, db_manager):
        """
        初始化 AI Agent (v1.0.0 寻猎者完全体)
        
        Args:
            db_manager: DatabaseManager 实例，用于访问配置和数据
        """
        self.db = db_manager
        self.llm_client = LLMClient(db_manager)
        
        # 初始化系统监控服务
        from app.services.system import MonitorService
        self.monitor = MonitorService(db_manager)
        
        # 候选等待状态：key=会话标识(固定"default"), value={candidates, query, media_type}
        logger.info("✅ [AIAgent] AI 内核已初始化 (v1.0.0 寻猎者引擎已装载)")
    
    @property
    def ai_name(self):
        """动态获取 AI 名称，确保实时同步"""
        return self.db.get_agent_config("ai_name", "AI 影音大师")
    
    @property
    def ai_persona(self):
        """动态获取 AI 人格，确保实时同步"""
        return self.db.get_agent_config("ai_persona", "你是一个专业的 NAS 影音库管理员")
    
    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """
        工业级 JSON 块提取器（V2 — 非贪婪 + Markdown 剥离 + 二次降级）

        设计目标：
        - 从 LLM 返回的文本中提取 JSON 对象
        - 兼容 Markdown 代码围栏（```json ... ```）
        - 容错处理：LLM 可能在 JSON 前后添加说明文字
        
        提取策略：
        1. 先剥离 ```json ... ``` / ``` ... ``` Markdown 围栏
        2. 用非贪婪正则提取最外层 {...} 块（从第一个 { 到最后一个 }）
        3. 若 json.loads 仍失败，记录原始片段便于调试

        Args:
            text: LLM 返回的文本

        Returns:
            Optional[Dict]: 解析后的 JSON 对象，失败返回 None
        """
        if not text:
            return None

        # ── 第一步：剥离 Markdown 代码围栏 ──────────────────────────
        # 匹配 ```json\n...\n``` 或 ```\n...\n``` 并取出内部内容
        fence_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text, re.DOTALL)
        cleaned = fence_match.group(1).strip() if fence_match else text

        # ── 第二步：提取最外层 JSON 对象（从第一个 { 到最后一个 }）──
        start = cleaned.find('{')
        end = cleaned.rfind('}')
        if start == -1 or end == -1 or end <= start:
            logger.warning(f"[Parser] 未找到有效 JSON 块，原始文本前 200 字符: {text[:200]}")
            return None

        json_str = cleaned[start:end + 1]

        # ── 第三步：尝试解析 ──────────────────────────────────────────
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"❌ [Parser] JSON 解析异常: {e} | 片段: {json_str[:300]}")
            return None
        except Exception as e:
            logger.error(f"❌ [Parser] 未知异常: {e}")
            return None
    
    def _sanitize_reply(self, text: str) -> str:
        """
        防御式净化中间件：优雅拦截 JSON 污染
        
        设计目标：
        - 如果 LLM 意外返回了 JSON 格式的回复，自动将其拆解为纯文本
        - 移除 Markdown 代码块标记残留
        - 确保前端展示的永远是纯净的自然语言
        
        拦截策略：
        1. 检测 JSON 字典格式（以 { 开头，以 } 结尾）
        2. 尝试解析 JSON，提取所有非空 value 拼接成换行文本
        3. 移除 Markdown 代码块标记（```json、```）
        
        Args:
            text: LLM 返回的原始文本
            
        Returns:
            str: 净化后的纯文本
        """
        text = text.strip()
        
        # 策略 1：检测并拆解 JSON 字典
        if text.startswith("{") and text.endswith("}"):
            try:
                data = json.loads(text)
                # 优雅地将 JSON 的 value 拼接成换行文本，丢弃 key
                # 过滤掉空值和纯结构字段（intent、reply 等可能为空）
                values = []
                for k, v in data.items():
                    # 跳过空值和单纯的意图/指令字段
                    if v and str(v).strip() and k not in ("intent", "reply", "action"):
                        values.append(str(v))
                
                # 如果拆解出了有意义的内容，使用拆解后的文本
                if values:
                    clean_text = "\n".join(values)
                    logger.info(f"[Sanitizer] JSON 污染已拦截并净化: {text[:50]}... -> {clean_text[:50]}...")
                    return clean_text
                else:
                    # JSON 中没有有意义的内容（都是空值或元数据），直接返回错误提示
                    logger.warning(f"[Sanitizer] JSON 结构为空或无意义内容，无法净化: {text}")
                    return ""
            except json.JSONDecodeError:
                pass
        
        # 策略 2：移除 Markdown 代码块标记残留
        text = text.replace("```json", "").replace("```", "").strip()
        
        return text

    def _match_candidate(self, user_input: str, candidates: list) -> Optional[dict]:
        """
        候选匹配辅助方法

        匹配优先级：
        1. 纯数字序号（如「1」）→ 按下标取候选；越界时不做模糊匹配
        2. 序号前缀（如「1. 绿巨人浩克」）→ 按前缀数字取候选
        3. 去年份精确匹配
        4. 去年份包含匹配（片名长度 ≥ 4 且存在于输入中）
        """
        stripped = user_input.strip()

        # 策略 1: 纯数字序号
        if stripped.isdigit():
            idx = int(stripped) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]
            return None  # 越界不降级做模糊匹配，与原逻辑一致

        # 策略 2: 序号前缀（如「1. 片名」「1、片名」）
        seq_match = re.match(r'^(\d+)[.、。]\s*', stripped)
        if seq_match:
            idx = int(seq_match.group(1)) - 1
            if 0 <= idx < len(candidates):
                return candidates[idx]

        # 策略 3 & 4: 片名模糊匹配（去年份括号后比较）
        _rm_year = lambda s: re.sub(r'\s*[\(（]\d{4}[\)）]\s*', '', s).strip()
        stripped_clean = _rm_year(stripped)

        for c in candidates:
            if stripped_clean == _rm_year(c["title"]):
                return c

        for c in candidates:
            title_clean = _rm_year(c["title"])
            if (stripped == c["title"]
                    or stripped_clean == title_clean
                    or (len(title_clean) >= 4
                        and title_clean in stripped_clean
                        and stripped_clean != title_clean)):
                return c

        return None

    async def process_message(self, user_message: str) -> Tuple[str, Optional[str]]:
        """
        用户消息处理核心方法

        处理流程：
        1. 候选拦截：若上一轮展示了候选列表，优先匹配用户选择，构造确认载荷
        2. 动态读取配置：获取 master_router_rules 与 ai_persona
        3. LLM 意图识别：调用大模型进行结构化意图识别
        4. 意图路由：根据识别结果路由到对应处理逻辑
        5. 规则引擎兜底：LLM 失败时使用本地规则引擎识别意图

        支持的意图：
        - ACTION_SCAN：物理扫描
        - ACTION_SCRAPE：全量刮削
        - ACTION_SUBTITLE：字幕补全
        - SYSTEM_STATUS：系统状态查询
        - DOWNLOAD：下载影片（统一经授权决策层确认后执行）
        - LOCAL_SEARCH：本地搜索
        - CHAT：普通闲聊

        Args:
            user_message: 用户输入的消息

        Returns:
            Tuple[str, Optional[str]]: (AI 回复文本, 意图指令代码)
        """
        # 🚀 第一步：动态获取用户的总控中枢规则和 AI 人格设定
        router_rules = self.db.get_agent_config("master_router_rules", "")
        ai_persona = self.db.get_agent_config("ai_persona", "")
        
        # ── 候选等待拦截：若上一轮展示了候选列表，优先匹配用户选择 ──
        # 从数据库读取候选状态（内存单例在 --reload 模式下不可靠）
        _pending_raw = self.db.get_config("_pending_candidates", "")
        pending = None
        if _pending_raw:
            try:
                pending = json.loads(_pending_raw)
            except Exception:
                pending = None
        logger.info(f"[AIAgent] 候选状态检查: pending={bool(pending)}, agent_id={id(self)}")
        if pending:
            candidates = pending["candidates"]  # List[{title, year, tmdb_id, media_type}]
            logger.info(f"[AIAgent] 候选匹配尝试: user_input={repr(user_message.strip())}, candidates={[c['title'] for c in candidates]}")
            chosen = self._match_candidate(user_message, candidates)
            if chosen:
                # 清除候选状态（数据库）
                self.db.set_config("_pending_candidates", "")
                logger.info(f"[AIAgent] 用户选择候选: {chosen['title']} ({chosen['year']})")

                # 授权决策层：将选定候选的元数据写入缓存，等待用户全屏确认后再执行下载
                # 严禁在此处直接调用 ServarrClient，下载由 /confirm 端点统一负责
                tmdb_api_key = self.db.get_config("tmdb_api_key", "").strip()
                poster_url = ""
                overview = ""
                if tmdb_api_key and chosen.get("id"):
                    try:
                        from app.services.metadata.adapters import TMDBAdapter
                        tmdb = TMDBAdapter(tmdb_api_key)
                        media_type_chosen = chosen.get("media_type", "movie")
                        # 使用 search_media 统一接口（含 /search/multi fallback）
                        # asyncio.to_thread 将同步阻塞 I/O 投入线程池，不阻塞事件循环
                        details = await asyncio.to_thread(
                            tmdb.search_media, chosen["title"],
                            media_type=media_type_chosen, year=chosen.get("year") or None
                        )
                        logger.info(f"[AIAgent] 候选元数据补全: media_type={media_type_chosen}, title={chosen['title']}")
                        # 精确匹配 tmdb_id
                        top = next((r for r in details if r.get("id") == chosen.get("id")), details[0] if details else {})
                        poster_path = top.get("poster_path", "")
                        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
                        overview = top.get("overview", "")
                    except Exception as e:
                        logger.warning(f"[AIAgent] 候选元数据补全失败: {e}")

                self._last_download_meta = {
                    "title":           chosen["title"],
                    "year":            str(chosen.get("year", "")),
                    "poster_url":      poster_url,
                    "overview":        overview,
                    "media_type":      chosen.get("media_type", "movie"),
                    "tmdb_id":         chosen.get("id"),
                    "clean_name":      chosen["title"],
                    "en_name":         "",
                    "is_duplicate":    False,
                    "existing_status": None,
                }
                # 查重审计：候选选择场景下同样执行库内状态检查
                if chosen.get("id"):
                    try:
                        from app.services.downloader import ServarrClient
                        servarr_check = ServarrClient(self.db)
                        dup_result = await servarr_check.check_existence(
                            chosen["id"], chosen.get("media_type", "movie")
                        )
                        self._last_download_meta["is_duplicate"]    = dup_result.get("exists", False)
                        self._last_download_meta["existing_status"] = dup_result.get("status")
                        if dup_result.get("exists"):
                            logger.info(f"[AIAgent] 候选查重命中: tmdb:{chosen['id']} -> {dup_result.get('status')}")
                    except Exception as e:
                        logger.warning(f"[AIAgent] 候选查重审计异常（非阻断）: {e}")
                
                # 持久化：同步写入数据库
                try:
                    self.db.set_config("_pending_download_meta", json.dumps(self._last_download_meta, ensure_ascii=False))
                except Exception as e:
                    logger.warning(f"[AIAgent] 候选元数据持久化失败（非阻断）: {e}")
                
                logger.info(f"[AIAgent] 候选元数据已缓存，等待授权: {chosen['title']} ({chosen.get('year', '')})")
                return f"找到「{chosen['title']}」({chosen.get('year', '')})，请在确认界面核对信息后授权下载。", self.DOWNLOAD
            else:
                # 反转判断逻辑：只有明确像「候选选择」时才保留状态，其余一律清除放行
                # 「像候选选择」的特征：纯数字、「序号.」格式、包含候选片名关键词
                import re as _re
                _looks_like_selection = (
                    bool(_re.match(r'^\d+$', stripped))  # 纯数字
                    or bool(_re.match(r'^\d+[.。、]', stripped))  # 序号. 格式
                    or any(  # 包含候选片名中的关键词（≥2字）
                        kw in stripped
                        for c in candidates
                        for kw in [c['title'][:4]] if len(c['title']) >= 2
                    )
                )
                if _looks_like_selection:
                    # 用户输入像候选选择但未能精确匹配，保留状态，提示重新选择
                    logger.info(f"[AIAgent] 候选匹配失败，保留候选状态，user_input={repr(stripped)}")
                    quick_opts = [f"{c['title']} ({c['year']})".strip() if c.get('year') else c['title'] for c in candidates]
                    reply = f"未能识别您的选择，请输入序号（如 1、2）或片名关键词。\n__CANDIDATES__{json.dumps(quick_opts, ensure_ascii=False)}"
                    return reply, None
                else:
                    # 其他任何意图（聊天/状态/扫描/查看日志等）一律清除候选状态放行
                    logger.info(f"[AIAgent] 检测到非候选选择意图，清除候选状态，放行至正常流程: {repr(stripped)}")
                    self.db.set_config("_pending_candidates", "")
                    # 不 return，继续往下走正常意图识别
        
        # 🚀 第二步：融合 System Prompt（将人格设定作为最高准则，附带总控路由契约）
        system_content = f"{ai_persona}\n\n{router_rules}".strip()
        
        # 🚀 第三步：优先使用 LLM 进行智能意图识别（如果总控规则存在）
        if router_rules.strip():
            try:
                # 单次调用：LLM 同时返回 intent + reply，消灭双重调用
                # 协议校验层：force_json=True 强制 JSON 输出（云端接口）
                intent_res = await self.llm_client.call_llm(
                    system_content,
                    f"指令串: {user_message}",
                    force_json=True,
                )
                intent_data = self._parse_json_response(intent_res)
                
                # 逻辑分发层：Dispatcher 白名单 + 参数强校验
                if intent_data:
                    from app.services.ai.dispatcher import Dispatcher, AIActionEnum
                    validated = Dispatcher.validate_intent(intent_data)
                    if validated is None:
                        # 校验未通过（非法意图/参数错误/频率限制），降级为 CHAT
                        logger.warning("[AIAgent] Dispatcher 校验失败，降级为 CHAT")
                        intent_data = {"intent": self.CHAT, "reply": ""}
                    else:
                        # 用校验后的规范化数据替换原始数据
                        intent_data = validated.model_dump()
                        intent_data["intent"] = validated.intent.value  # 枚举转字符串

                if intent_data:
                    intent = intent_data.get("intent", self.CHAT)
                    llm_reply = (intent_data.get("reply") or "").strip()

                    # ── 技术动作：零 Token，本地模板直接返回 ──────────────
                    _ACTION_TEMPLATES = {
                        self.ACTION_SCAN:     "好的，物理扫描已启动，稍后刷新页面查看新增文件。",
                        self.ACTION_SCRAPE:   "收到，全量刮削任务已下发，刮削完成后媒体信息将自动更新。",
                        self.ACTION_SUBTITLE: "明白，字幕补全任务已启动，将为缺失字幕的文件重新检索。",
                    }
                    if intent in _ACTION_TEMPLATES:
                        response_text = llm_reply if llm_reply else _ACTION_TEMPLATES[intent]
                        return response_text, intent

                    # ── SYSTEM_STATUS / DOWNLOAD / CHAT：走原有富逻辑生成 ──
                    # 重要：对于这些复杂意图，不能使用第一次 JSON 中的 reply 字段（那是空的），
                    # 必须重新调用 LM 获取完整答案
                    result = await self._generate_llm_response(user_message, intent_data, router_rules)
                    # 结构化候选列表：返回三元组 (text, sentinel, candidates)
                    if isinstance(result, tuple) and len(result) == 3:
                        response_text, sentinel, candidates_data = result
                        if sentinel == "__CANDIDATES_STRUCTURED__":
                            return response_text, None, candidates_data
                    else:
                        response_text = result

                    # 旧版文本标记兼容（理论上不再触发）
                    if "__CANDIDATES__" in response_text:
                        return response_text, None
                    action_code = intent if intent != self.CHAT else None
                    return response_text, action_code
            except Exception as e:
                logger.error(f"[AIAgent] LLM 意图识别失败，启动兜底防线: {e}")
        
        # 🚨 兜底防线（Fallback）：使用规则引擎识别意图
        logger.warning("[AIAgent] 总控规则为空或 LLM 调用失败，使用关键词匹配兜底")
        intent_data = self._recognize_intent(user_message)
        intent = intent_data.get("intent", self.CHAT)
        
        # 🚨 统一出口：降级方案也使用 _generate_llm_response
        result = await self._generate_llm_response(user_message, intent_data, router_rules)
        if isinstance(result, tuple) and len(result) == 3:
            response_text, sentinel, candidates_data = result
            if sentinel == "__CANDIDATES_STRUCTURED__":
                return response_text, None, candidates_data
        else:
            response_text = result

        # 候选列表展示时不下发 action_code
        if "__CANDIDATES__" in response_text:
            return response_text, None
        # 返回响应文本和意图代码
        action_code = intent if intent != self.CHAT else None
        
        return response_text, action_code
    
    async def _generate_llm_response(self, message: str, intent_data: Dict, router_rules: str = "") -> str:
        """
        使用 LLM 生成智能响应（总控中枢神经接通版）
        
        总控契约：
        1. 日常对话管线只注入 ai_persona 与 master_router_rules，保持 Prompt 物理隔离
        2. 非模板类意图走 LLM 动态生成，替代静态应答
        3. 系统状态类意图附带运行快报上下文，约束输出与观测数据对齐
        
        Args:
            message: 用户消息
            intent_data: 意图数据
            router_rules: 总控中枢规则，仅来自 master_router_rules
            
        Returns:
            str: AI 响应文本
        """
        intent = intent_data.get("intent")
        
        # 🚀 第一步：动态获取 AI 名称 + 人格设定，拼装日常对话基础 System Prompt
        ai_name = self.ai_name
        ai_persona_raw = self.ai_persona
        ai_persona = f"你的名字是「{ai_name}」。{ai_persona_raw}" if ai_persona_raw else f"你的名字是「{ai_name}」。"
        base_system_prompt = f"{ai_persona}\n\n{router_rules}".strip()
        
        # 🚀 第二步：全时态感知 - 为所有对话注入系统运行快报
        stats = self._get_system_stats()
        status_summary = f"[实时现状] 总文件:{stats['total']}, 已归档:{stats['archived']}"
        
        if intent in (self.ACTION_SCAN, self.ACTION_SCRAPE, self.ACTION_SUBTITLE):
            # 技术动作：零 Token，本地模板直接返回（process_message 已处理，此处作为 fallback 兜底）
            _ACTION_TEMPLATES = {
                self.ACTION_SCAN:     "物理扫描指令已透传，后台任务已启动。",
                self.ACTION_SCRAPE:   "全量刮削指令已下达，元数据更新流程已启动。",
                self.ACTION_SUBTITLE: "字幕补全指令已执行，检索任务已进入队列。",
            }
            return _ACTION_TEMPLATES.get(intent, "指令已接收，任务已启动。")
        
        elif intent == self.SYSTEM_STATUS:
            # ==========================================
            # 📊 系统状态查询（全时态感知 + 物理感知）
            # ==========================================
            # 设计目标：提供实时、准确的系统运行状态
            # 
            # 数据来源：
            # 1. 数据库统计：tasks 表 + media_archive 表
            # 2. 系统日志：最近 30 行日志
            # 3. 磁盘占用：真实的磁盘使用率
            # 4. 服务心跳：Radarr/Sonarr 在线状态（新增）
            # 
            # 真理宣言：
            # - 绝对禁止编造任何数字
            # - 必须使用实时系统快报中的真实数据
            # - 如果某项数据为 0，必须如实说明
            # 
            # 核心概念：
            # - archived：已完成刮削 + 文件搬运 + 海报下载
            # - scraped：已获取元数据但尚未完成搬运
            # - pending：等待刮削的任务
            # - failed：刮削或搬运失败的任务
            # - ignored：重复文件或手动跳过的任务
            # ==========================================
            # 第一步：获取真实系统统计数据
            stats = self._get_system_stats()
            all_data = self.db.get_all_data()
            recent = [t for t in all_data if t.get("status") == "archived"][:10]
            ignored_count = len([t for t in all_data if t.get("status") == "ignored"])
            
            # 第二步：系统感官集成 - 从统一监控服务获取物理硬件状态快照
            try:
                health = await self.monitor.get_system_status()
                disk_status_text = f"{health['disk_free_gb']}GB 可用 / {health['disk_total_gb']}GB 总容量 ({health['disk_usage_percent']}% 已用)"
                disk_alert = ""
                if health['disk_status'] == "CRITICAL":
                    disk_alert = " ⚠️ CRITICAL - 磁盘空间严重不足！"
                elif health['disk_status'] == "WARNING":
                    disk_alert = " ⚠️ WARNING - 磁盘空间偏低"
                
                radarr_text = {
                    "ONLINE": "🟢 在线",
                    "OFFLINE": "🔴 离线",
                    "NOT_CONFIGURED": "⚪ 未配置"
                }.get(health['services']['radarr'], "❓ 未知")
                
                sonarr_text = {
                    "ONLINE": "🟢 在线",
                    "OFFLINE": "🔴 离线",
                    "NOT_CONFIGURED": "⚪ 未配置"
                }.get(health['services']['sonarr'], "❓ 未知")
                
                cpu_text = f"{health['cpu_usage_percent']}%"
            except Exception as e:
                logger.warning(f"[SYSTEM_STATUS] 物理感知数据获取失败: {e}")
                disk_status_text = "磁盘状态获取失败"
                disk_alert = ""
                radarr_text = "❓ 检测失败"
                sonarr_text = "❓ 检测失败"
                cpu_text = "N/A"
            
            # 第三步：读取真实日志
            log_content = self._read_recent_logs(30)
            
            # 第四步：构建【实时系统快报】（强制约束 LLM 使用真实数据）
            context_report = f"""【实时系统快报 - 绝对禁止编造数据】

数据库总任务数：{stats['total']} 个
🟢 已成功入库 (archived)：{stats['archived']} 个
📦 已刮削 (scraped)：{stats['scraped']} 个
⏳ 待处理队列 (pending)：{stats['pending']} 个
❌ 匹配/处理失败 (failed)：{stats['failed']} 个
⚪ 已跳过重复项 (ignored)：{ignored_count} 个

【物理感知数据】
💾 磁盘状态：{disk_status_text}{disk_alert}
🖥️ CPU 使用率：{cpu_text}
📡 Radarr 服务：{radarr_text}
📡 Sonarr 服务：{sonarr_text}

【最近成功入库的影视（最多 10 条）】
{self._format_recent_tasks(recent)}

【最近系统日志（最后 30 行）】
{log_content}
"""
            
            # 第四步：融合 AI 人格 + 真理宣言 + 实时快报
            full_system_prompt = f"""{base_system_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【🚨 真理宣言：数据真实性铁律 🚨】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ 绝对禁止编造任何数字！
⚠️ 你必须且只能根据下方【实时系统快报】中的真实数据进行汇报！
⚠️ 如果快报显示某项数据为 0，你必须如实说明为 0，不得虚构！
⚠️ 如果 archived 为 0，你必须明确说"当前暂无成功入库的文件"！
⚠️ 如果 total 为 0，你必须说"媒体库当前为空"！
⚠️ 磁盘占用率必须使用快报中的真实数值，不得估算或编造！

【核心概念理解】
- "archived" (已归档) = 已 100% 完成 TMDB 刮削 + 文件硬链接搬运 + 海报下载
- "scraped" (已刮削) = 已获取元数据但尚未完成文件搬运
- "pending" (待处理) = 等待刮削的任务
- "failed" (失败) = 刮削或搬运失败的任务
- "ignored" (已跳过) = 重复文件或手动跳过的任务

【汇报规则】
1. 用简明扼要、专业的语言汇报当前媒体库的整体情况
2. 如果 pending 或 failed 为 0，表扬系统运行健康
3. 如果有 pending 或 failed，提醒用户还有待处理任务
4. 结合日志简单提一句最近系统在干什么
5. 绝对不要输出长篇大论的 Markdown 表格，用精炼的要点列表即可
6. 必须使用快报中的真实磁盘占用率数值

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{context_report}

请严格遵守【真理宣言】，根据上面的【实时系统快报】生成状态汇报。"""
            
            # 调用 LLM 生成响应，传入完整的 system_prompt
            # 关键：不能再使用 force_json=True，必须获取自然语言响应
            ai_response = await self.llm_client.call_llm(full_system_prompt, message, force_json=False)
            # 防御式净化：拦截可能的 JSON 污染（如果LM仍然返回了JSON格式）
            cleaned = self._sanitize_reply(ai_response)
            # 如果净化后仍为空，返回系统快报摘要
            if not cleaned or not cleaned.strip():
                logger.warning("[SYSTEM_STATUS] LM 响应为空，返回系统快报摘要")
                return f"【系统快速汇报】\n总任务数: {stats['total']}\n已完成: {stats['archived']}\n待处理: {stats['pending']}\n失败: {stats['failed']}"
            return cleaned
        
        elif intent == self.DOWNLOAD:
            # ==========================================
            # 🚀 v1.0.0 寻猎者引擎（Hunter Engine）
            # ==========================================
            # 设计目标：智能下载影片，支持模糊意图和精确匹配
            # 
            # 核心流程：
            # 1. 从 LLM 返回的 JSON 中提取结构化数据（片名、类型、年份）
            # 2. 序号归一：将用户原话末尾部/集序号并入结构化片名，与 LLM 抽取结果对齐
            # 3. 模糊意图处理：无年份且无序号时，查询 TMDB 候选列表让用户选择
            # 4. 调用 Servarr 客户端（Radarr/Sonarr）下发下载任务
            # 5. 返回下载结果或候选列表
            # 
            # 候选列表机制：
            # - 触发条件：无年份 + 无序号（如「我想看蜘蛛侠」）
            # - 查询 TMDB：按热度排序返回前 5 条结果
            # - 保存状态：将候选列表存入数据库（跨请求持久化）
            # - 用户选择：下次对话时匹配用户输入的序号或片名
            # 
            # 序号派生规则：
            # - 当 clean_name 未含部/集序号时，从用户原话尾部解析（中文或阿拉伯数字）
            # - 与 clean_name 去重合并，避免重复缀号
            # ==========================================
            # 1. 从 intent_data 中提取结构化数据
            clean_name = intent_data.get("clean_name", "").strip()
            en_name = intent_data.get("en_name", "").strip()  # 80B 提供的英文名，优先用于 TMDB 搜索
            media_type = intent_data.get("media_type", "movie").strip().lower()  # 契约：意图 JSON 使用 media_type，与历史 type 字段区分
            year = intent_data.get("year", "").strip()
            # TMDB 搜索优先用英文名（准确），无英文名时用中文名
            search_name = en_name if en_name else clean_name
            logger.info(f"[DOWNLOAD] 提取意图 -> 片名: {clean_name}, 类型: {media_type}, 年份: {year}")

            # 序号派生：clean_name 缺尾缀序号且用户消息尾部可解析部/集号时，并入片名
            if clean_name and not year:
                import re as _re
                # 中文数字映射
                _CN_NUM = {'一': '1', '二': '2', '三': '3', '四': '4', '五': '5',
                           '六': '6', '七': '7', '八': '8', '九': '9', '十': '10'}
                # 从原始消息提取末尾序号（中文或阿拉伯数字）
                seq_match = _re.search(
                    r'第?\s*([一二三四五六七八九十]|\d{1,2})\s*[部集季]?\s*$',
                    message.strip()
                )
                if seq_match:
                    raw_seq = seq_match.group(1)
                    seq_num = _CN_NUM.get(raw_seq, raw_seq)  # 中文数字转阿拉伯
                    # 检查 clean_name 里是否已经含有该序号（避免重复）
                    existing = _re.search(r'\b' + seq_num + r'\b', clean_name)
                    # 同时检查 clean_name 里是否含有中文序号对应词
                    cn_key = next((k for k, v in _CN_NUM.items() if v == seq_num), None)
                    existing_cn = cn_key and cn_key in clean_name
                    if not existing and not existing_cn:
                        clean_name = f"{clean_name} {seq_num}"
                        logger.info(f"[DOWNLOAD] 序号补全: '{intent_data.get('clean_name')}' -> '{clean_name}'")
                    else:
                        # LLM 已经把序号放进了 clean_name，去掉可能的中文数字残留
                        clean_name = _re.sub(r'[一二三四五六七八九十]', '', clean_name).strip()
                        logger.info(f"[DOWNLOAD] 序号已存在，清理中文数字: '{clean_name}'")
            
            # 2. 容错处理：如果提取失败，使用 LLM 生成引导语
            if not clean_name:
                logger.warning(f"[DOWNLOAD] 意图数据提取失败，原始数据: {intent_data}")
                prompt = f"{ai_persona}\n\n用户想下载影片，但未能识别出片名，请用简短的一句话引导用户重新输入。"
                return await self.llm_client.call_llm(prompt, message)

            # 2.5 模糊意图处理：无论有无年份/序号，所有新搜索强制走候选列表流程
            # 严禁在此直接构造 PendingActionPayload（剥夺自动弹窗权）
            import re as _re2
            has_seq = bool(_re2.search(r'\d', clean_name))
            _candidate_query = en_name if en_name else clean_name

            # 执行 TMDB 搜索（用于候选列表）
            _search_candidates = await self._tmdb_search_candidates(_candidate_query, media_type=media_type, year=year)

            # 若有年份或序号，也直接返回候选（可能只有 1 个），由用户点击确认
            if _search_candidates:
                logger.info(f"[DOWNLOAD] 强制候选流程，共 {len(_search_candidates)} 个结果: {[c['title'] for c in _search_candidates]}")
                _pending_data = {
                    "candidates": _search_candidates,
                    "query": clean_name,
                    "media_type": media_type,
                }
                self.db.set_config("_pending_candidates", json.dumps(_pending_data, ensure_ascii=False))
                logger.info(f"[AIAgent] 候选状态已写入数据库: {len(_search_candidates)} 条, agent_id={id(self)}")
                ai_text = f"为您找到以下结果，请点击选择："
                return ai_text, "__CANDIDATES_STRUCTURED__", _search_candidates

            # 若 TMDB 无结果，提示用户
            if not _search_candidates:
                return f"未在 TMDB 找到「{clean_name}」的相关结果，请确认片名后重试。"

            # 3. 类型归一化处理（后续代码保留作兜底，实际不应再被执行）
            if media_type not in ["movie", "tv"]:
                media_type = "movie"
            
            logger.info(f"[DOWNLOAD] 提取意图 -> 片名: {clean_name}, 类型: {media_type}, 年份: {year}")
            
            # 4. 查询 TMDB 元数据，构造下载确认载荷（授权决策层）
            # 不在此处执行下载，而是将元数据写入 _last_download_meta
            # 真正的下载由 /confirm 端点在用户授权后触发
            try:
                tmdb_api_key = self.db.get_config("tmdb_api_key", "").strip()
                if tmdb_api_key:
                    from app.services.metadata.adapters import TMDBAdapter
                    tmdb = TMDBAdapter(tmdb_api_key)
                    # 使用 search_media 统一接口（含 /search/multi fallback）
                    # asyncio.to_thread 将同步阻塞 I/O 投入线程池，不阻塞事件循环
                    results = await asyncio.to_thread(
                        tmdb.search_media, search_name,
                        media_type=media_type, year=year if year else None
                    )
                    logger.info(f"[DOWNLOAD] TMDB 元数据查询: media_type={media_type}, search_name={search_name}")
                    results.sort(key=lambda r: r.get("popularity", 0), reverse=True)
                    top = results[0] if results else {}
                    confirmed_title = top.get("title") or top.get("name") or clean_name
                    rd = top.get("release_date") or top.get("first_air_date") or ""
                    confirmed_year = rd[:4] if rd else year
                    poster_path = top.get("poster_path", "")
                    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
                    overview = top.get("overview", "")
                    tmdb_id = top.get("id")
                else:
                    confirmed_title = clean_name
                    confirmed_year = year
                    poster_url = ""
                    overview = ""
                    tmdb_id = None
            except Exception as e:
                logger.warning(f"[DOWNLOAD] TMDB 元数据查询失败: {e}，使用原始片名")
                confirmed_title = clean_name
                confirmed_year = year
                poster_url = ""
                overview = ""
                tmdb_id = None

            # 将元数据写入实例属性，供 endpoints/agent.py 读取封装为 PendingActionPayload
            # 同步执行查重审计：在构造确认载荷前检查资源是否已在 Radarr/Sonarr 库中
            is_duplicate = False
            existing_status = None
            if tmdb_id:
                try:
                    from app.services.downloader import ServarrClient
                    servarr_check = ServarrClient(self.db)
                    dup_result = await servarr_check.check_existence(tmdb_id, media_type)
                    is_duplicate   = dup_result.get("exists", False)
                    existing_status = dup_result.get("status")
                    if is_duplicate:
                        logger.info(f"[DOWNLOAD] 查重审计命中: tmdb:{tmdb_id} -> {existing_status}")
                    else:
                        logger.info(f"[DOWNLOAD] 查重审计通过: tmdb:{tmdb_id} 不在库中")
                except Exception as e:
                    logger.warning(f"[DOWNLOAD] 查重审计异常（非阻断）: {e}")

            self._last_download_meta = {
                "title":           confirmed_title,
                "year":            confirmed_year,
                "poster_url":      poster_url,
                "overview":        overview,
                "media_type":      media_type,
                "tmdb_id":         tmdb_id,
                "clean_name":      clean_name,
                "en_name":         en_name,
                "is_duplicate":    is_duplicate,
                "existing_status": existing_status,
            }
            
            # 持久化：同步写入数据库，应对进程重启场景
            try:
                self.db.set_config("_pending_download_meta", json.dumps(self._last_download_meta, ensure_ascii=False))
            except Exception as e:
                logger.warning(f"[DOWNLOAD] 元数据持久化失败（非阻断）: {e}")
            
            logger.info(f"[DOWNLOAD] 元数据已缓存，等待用户授权: {confirmed_title} ({confirmed_year})")

            # 返回引导文本（前端将同步渲染全屏确认界面）
            return f"找到「{confirmed_title}」({confirmed_year})，请在确认界面核对信息后授权下载。"
        
        elif intent == self.LOCAL_SEARCH:
            # 本地搜索确认语直接拼接，不调 LLM
            return f"正在本地媒体库中搜索，{status_summary}，请稍候。"
        
        else:  # CHAT
            # 🚀 全时态感知：普通聊天只注入人格、总控规则与系统现状
            prompt = f"{base_system_prompt}\n\n当前系统状态：{status_summary}\n\n执行专业闲聊回复。"
            response = await self.llm_client.call_llm(prompt, message)
            # 防御式净化：拦截可能的 JSON 污染
            return self._sanitize_reply(response)

    def _read_recent_logs(self, lines: int = 30) -> str:
        """
        读取最近的系统日志
        """
        import os
        try:
            # 策略一：从 db_path 反推 data/logs/app.log
            db_path = getattr(self.db, 'db_path', None)
            if db_path:
                log_path = os.path.join(os.path.dirname(str(db_path)), 'logs', 'app.log')
                if os.path.exists(log_path):
                    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                        all_lines = f.readlines()
                        return ''.join(all_lines[-lines:])
            # 策略二：从当前文件向上查找 backend 目录（Docker/WSL/Windows 通用）
            current_file = Path(__file__).resolve()
            for parent in list(current_file.parents[:6]):
                if parent.name == 'backend' and parent.is_dir():
                    dynamic_path = str(parent / 'data' / 'logs' / 'app.log')
                    if os.path.exists(dynamic_path):
                        with open(dynamic_path, 'r', encoding='utf-8', errors='ignore') as f:
                            all_lines = f.readlines()
                            return ''.join(all_lines[-lines:])
                    break
            # 策略三：Docker 固定路径兜底
            docker_path = '/app/data/logs/app.log'
            if os.path.exists(docker_path):
                with open(docker_path, 'r', encoding='utf-8', errors='ignore') as f:
                    all_lines = f.readlines()
                    return ''.join(all_lines[-lines:])
            return '（日志文件未找到）'
        except Exception as e:
            return f'（读取日志失败: {e}）'

    async def _tmdb_search_candidates(
        self, name: str, media_type: str, year: str = ""
    ) -> list:
        """
        查询 TMDB 候选列表，按热度排序返回前 5 条结果供用户选择
        """
        try:
            tmdb_api_key = self.db.get_config("tmdb_api_key", "").strip()
            if not tmdb_api_key:
                return []
            from app.services.metadata.adapters import TMDBAdapter
            tmdb = TMDBAdapter(tmdb_api_key)
            # 使用统一搜索入口：动态路由 + /search/multi fallback
            # asyncio.to_thread 将同步阻塞 I/O 投入线程池，不阻塞事件循环
            results = await asyncio.to_thread(
                tmdb.search_media, name,
                media_type=media_type, year=year if year else None
            )
            # 按 popularity 降序排序（热度高的优先）
            results.sort(key=lambda r: r.get("popularity", 0), reverse=True)
            candidates = []
            for r in results[:5]:
                # 兼容电影(title)和剧集(name)的字段差异
                title = r.get("title") or r.get("name") or ""
                if not title:
                    continue
                # 兼容电影(release_date)和剧集(first_air_date)的字段差异
                rd = r.get("release_date") or r.get("first_air_date") or ""
                yr = rd[:4] if rd else ""
                # 从结果中获取真实 media_type（/search/multi 会携带此字段）
                real_media_type = r.get("media_type") or media_type
                if real_media_type == "person":
                    continue  # 防御性过滤
                candidates.append({
                    "title": title,
                    "year": yr,
                    "id": r.get("id"),
                    "popularity": round(r.get("popularity", 0), 1),
                    "media_type": real_media_type,
                })
            logger.info(f"[AIAgent] 候选构造完成: {[(c['title'], c['media_type']) for c in candidates]}")
            return candidates
        except Exception:
            return []

    def _format_recent_tasks(self, tasks: list) -> str:
        """将最近任务列表格式化为可读文本"""
        if not tasks:
            return "暂无最近完成记录。"
        lines = []
        for t in tasks:
            status = t.get("status", "")
            name = t.get("name") or t.get("path") or t.get("title") or "(无名称)"
            if isinstance(name, str) and len(name) > 60:
                name = name[:57] + "..."
            lines.append(f"  - [{status}] {name}")
        return "\n".join(lines)

    def _recognize_intent(self, message: str) -> Dict:
        """
        识别用户消息的意图（规则引擎降级方案 - 强化版）
        
        核心改进：
        1. 扩充关键词库，提升意图识别准确率
        2. 优先级排序，避免误判
        
        Args:
            message: 用户消息
            
        Returns:
            Dict: 包含 intent 和其他相关参数的字典
        """
        msg_lower = message.lower()
        
        # 🎯 第二步：强化意图识别 - 扫描意图检测（优先级最高）
        scan_keywords = [
            "扫描", "发现", "新文件", "新资源", "检测文件", "物理扫描", 
            "扫描文件", "找新电影", "找新剧", "scan", "detect"
        ]
        if any(kw in msg_lower for kw in scan_keywords):
            return {"intent": self.ACTION_SCAN}
        
        # 刮削意图检测
        scrape_keywords = [
            "刮削", "整理", "元数据", "更新信息", "全量刮削", 
            "匹配封面", "找元数据", "获取信息", "scrape", "metadata"
        ]
        if any(kw in msg_lower for kw in scrape_keywords):
            return {"intent": self.ACTION_SCRAPE}
        
        # 字幕意图检测
        subtitle_keywords = ["字幕", "subtitle", "补全字幕", "下载字幕"]
        if any(kw in msg_lower for kw in subtitle_keywords):
            return {"intent": self.ACTION_SUBTITLE}
        
        # 系统状态查询（强化关键词）
        status_keywords = [
            "状态", "统计", "汇报", "战况", "任务", "失败", "成功", 
            "日志", "运行记录", "报错信息", "错误日志", "status", "log"
        ]
        if any(kw in msg_lower for kw in status_keywords):
            return {"intent": self.SYSTEM_STATUS}
        
        # 下载意图检测（v1.0.0 寻猎者增强版）
        download_keywords = ["下载", "想看", "找片", "搜索", "download"]
        if any(kw in msg_lower for kw in download_keywords):
            # 提取片名和类型
            media_name = self._extract_media_name(message)
            media_type = self._detect_media_type(message)
            year = self._extract_year(message)
            
            # 下载意图返回体契约：片名字段固定为 clean_name，供下游 Hunter 引擎消费
            return {
                "intent": self.DOWNLOAD,
                "clean_name": media_name,
                "media_type": media_type,
                "year": year
            }
        
        # 本地搜索
        search_keywords = ["本地", "库里", "有没有", "是否有", "local"]
        if any(kw in msg_lower for kw in search_keywords):
            return {"intent": self.LOCAL_SEARCH}
        
        # 默认为普通聊天
        return {"intent": self.CHAT}
    

    
    def _get_system_stats(self) -> Dict:
        """
        获取系统统计数据（双表合并版）

        数据来源：
        1. tasks 表：pending / failed 等待处理中的任务
        2. media_archive 表：已归档的完成记录（archived）

        Returns:
            Dict: 包含 total, archived, pending, failed, scraped
        """
        try:
            # ── 第一步：从 tasks 表获取待处理任务统计 ──
            pending_tasks = self.db.get_all_data()
            pending = len([t for t in pending_tasks if t.get("status") == "pending"])
            failed  = len([t for t in pending_tasks if t.get("status") == "failed"])
            scraped = len([t for t in pending_tasks if t.get("status") == "scraped"])

            # ── 第二步：从 media_archive 表获取归档统计（真实完成数据）──
            archive_stats = self.db.get_archive_stats()
            archived = archive_stats.get("total", 0)
            total = archived + pending + failed + scraped

            return {
                "total": total,
                "scraped": scraped,
                "archived": archived,
                "pending": pending,
                "failed": failed,
            }
        except Exception as e:
            logger.error(f"[AIAgent] 获取统计数据失败: {e}")
            return {
                "total": 0,
                "scraped": 0,
                "archived": 0,
                "pending": 0,
                "failed": 0,
            }
    
    def _extract_media_name(self, message: str) -> str:
        """从消息中提取影片名称"""
        keywords = ["下载", "想看", "找", "搜索", "有没有"]
        for kw in keywords:
            if kw in message:
                parts = message.split(kw)
                if len(parts) > 1:
                    name = parts[1].strip()
                    name = re.sub(r'[？?！!。，,]', '', name)
                    return name
        return message.strip()
    
    def _detect_media_type(self, message: str) -> str:
        """检测媒体类型"""
        msg_lower = message.lower()
        
        movie_keywords = ["电影", "大片", "movie", "film"]
        tv_keywords = ["剧", "动漫", "番剧", "tv", "series", "anime"]
        
        if any(kw in msg_lower for kw in movie_keywords):
            return "movie"
        elif any(kw in msg_lower for kw in tv_keywords):
            return "tv"
        else:
            return "auto"
    
    def _extract_year(self, message: str) -> str:
        """提取年份"""
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', message)
        if year_match:
            return year_match.group(1)
        return ""

    async def ai_identify_media(
        self, cleaned_name: str = "", full_path: str = "", type_hint: str = "movie",
        keyword_hint: Optional[str] = None,
        locked_season: Optional[int] = None,
        locked_episode: Optional[int] = None,
        raw_filename: str = "",
        parent_dir: str = "",
        sibling_files: Optional[list[str]] = None,
    ) -> Optional[Dict]:
        """
        AI 归档专家：影视文件语义识别引擎。

        设计目标：
        - 根据原始文件名、完整路径、父目录和同级文件样本提取 TMDB 搜索所需字段。
        - 输出片名查询词、媒体类型、季集坐标、文件名年份、知识库年份和证据对象。
        - 为后续 TMDB 搜索、防重和归档链路提供结构化输入。

        识别策略：
        1. `keyword_hint` 拥有最高优先级，代表用户显式人工判断。
        2. 父目录和同级文件样本作为上下文信号，帮助区分电影、剧集和绝对集号。
        3. 年份拆分为 `filename_year` 与 `knowledge_year`，由调用方执行证据镜像校验。
        4. LLM 输出必须符合强 Schema；调用方不再依赖旧版 RegexLab / DB 正则作为语义清洗兜底。

        Args:
            cleaned_name: 兼容字段。调用方传入的轻量结构化名称，不代表语义真理。
            full_path: 完整文件路径。
            type_hint: 路径或任务侧提供的类型提示（movie/tv）。
            keyword_hint: 用户手动输入的正确片名（最高优先级，直接覆盖 AI 推断）。
            locked_season: 外部已锁定的季号（可选）。
            locked_episode: 外部已锁定的集号（可选）。
            raw_filename: 原始文件名。
            parent_dir: 父目录名称。
            sibling_files: 同级视频文件名样本。

        Returns:
            Optional[Dict]: 成功时返回结构化识别结果；模型不可用或输出不合约时返回 None / 抛出上游异常，由刮削链路 Fail-Fast 处理。
        """
        # 🚀 第一步：动态获取用户的归档专家规则（DEFAULT_CONFIG 提供钢铁兜底，绝不为空）
        expert_rules = self.db.get_agent_config("expert_archive_rules", "")

        # ══ keyword_hint 快速通道（最高优先级）══════════════════════════
        # 若调用方传入了用户手动填写的正确片名，跳过 AI 推断，直接返回。
        # 这是「人在回路」机制的入口：人的判断永远高于 AI 猜测。
        if keyword_hint and keyword_hint.strip():
            _hint = keyword_hint.strip()
            logger.info(f"[AI][KEYWORD_HINT] 使用用户提供的片名覆盖 AI 推断: '{_hint}'")
            return {
                "query":          _hint,
                "type":           (type_hint or "movie").strip().lower() or "movie",
                "season":         None,
                "episode":        None,
                "filename_year":  "",
                "knowledge_year": "",
                "confidence": 1.0,
                "evidence": {"query_source": "keyword_hint"},
                "episode_numbering_mode": "unknown",
                "needs_review": False,
            }
        # ══════════════════════════════════════════════════════════════
        
        # 🚀 第二步：从完整路径提取父目录名作为额外线索
        # 例：'/download/tv/The Boys/Season 03/The.Boys.S03E01.mkv' → 'The Boys'
        parent_dir_hint = parent_dir or ""
        try:
            import os as _os
            path_parts = full_path.replace("\\", "/").split("/") if full_path else []
            if not raw_filename and path_parts:
                raw_filename = path_parts[-1]
            if not parent_dir_hint:
                for part in reversed(path_parts[:-1]):
                    part = part.strip()
                    if part and not re.match(r'^[Ss]eason\s*\d+$', part, re.IGNORECASE):
                        parent_dir_hint = part
                        break
        except Exception:
            pass

        raw_filename = raw_filename or cleaned_name or ""
        sibling_files = sibling_files or []
        sibling_sample = sibling_files[:20]
        schema_contract = (
            "\n\n【强 Schema 输出契约补丁 - 调用方强制】\n"
            "你必须且只能输出一个 JSON 对象，必须包含以下字段："
            "query,type,season,episode,filename_year,knowledge_year,confidence,evidence,episode_numbering_mode,needs_review。\n"
            "confidence 必须是 0 到 1 的数字；evidence 必须是对象；"
            "episode_numbering_mode 只能是 absolute、season_episode、unknown 之一。\n"
            "若 type=tv，season 与 episode 必须为整数或 null。"
            "没有明确 Season 2/S02/2x 证据时，纯数字后缀 01/02/10 必须解释为绝对集号：season=1, episode=该数字。\n"
            "严禁把纯数字 02 单独解释为第二季。"
        )

        # 🚀 第三步：调用底层 LLM 客户端（确保 JSON 强制输出）
        # prefer_local=True：将文件清洗任务卸载给本地边缘模型（高并发无情解析，不占用云端配额）
        # 本地未配置时自动回退云端，高可用保证
        raw = await self.llm_client.call_llm(
            system_prompt=f"{expert_rules}{schema_contract}",
            prefer_local=True,
            user_prompt=(
                f"请分析以下影视文件，并严格按照 System Prompt 中定义的规则与 JSON 契约输出。\n\n"
                f"【待分析事实】\n"
                f"原始文件名: {raw_filename}\n"
                f"文件路径: {full_path}\n"
                f"父目录名: {parent_dir_hint}\n"
                f"同级文件列表样本: {sibling_sample}\n"
                f"同级文件总数: {len(sibling_files)}\n"
                f"旧清洗名(仅兼容参考，禁止作为唯一真相): {cleaned_name}\n"
                f"类型提示: {type_hint or 'movie'}"
            )
        )
        
        # 🚀 第四步：解析 LLM 返回的 JSON（剔除 ```json ... ``` 包裹符号）
        data = self._parse_json_response(raw)
        
        # ── v1.0.0 弹性语义审计：三级置信度分类器 ──────────────────────
        # 幻觉词集合（触发分级处理而非直接拦截）
        _HALLUCINATION_WORDS = {
            "unknown", "n/a", "n/a.", "temp", "untitled", "null",
            "none", "undefined", "movie", "film", "video", "media",
            "content", "file", ""
        }

        def _classify_result(d: dict) -> str:
            """
            对 LLM 返回结果进行三级置信度分类：
              PASS    - query 有效，直接使用
              REPAIR  - query 为幻觉词但 year 有效，以 cleaned_name 重写 query 后放行
              FAIL    - query 和 year 均无效，触发云端降级
            """
            q = (d.get("query") or d.get("clean_name") or "").strip().lower()
            y = (d.get("knowledge_year") or d.get("year") or "").strip()
            year_valid = bool(y and re.fullmatch(r'(18|19|20)\d{2}', y))

            # Level 1 — 直接放行：query 非空且不在幻觉词表，长度 ≥ 2
            if q and q not in _HALLUCINATION_WORDS and len(q.replace(" ", "")) >= 2:
                return "PASS"

            # Level 2 — 置信度重整：query 落入幻觉词表且 year 有效，走 REPAIR 分支
            if year_valid:
                return "REPAIR"

            # Level 3 — 真·失败：query 和 year 均无效
            return "FAIL"

        # Fail-Fast：JSON 解析失败时不允许用 cleaned_name 兜底继续执行 TMDB 搜索
        if not data:
            raise RuntimeError("ai_json_parse_failed")

        required_schema_fields = ("confidence", "evidence", "episode_numbering_mode")
        missing_schema_fields = [field for field in required_schema_fields if field not in data]
        if missing_schema_fields:
            raise RuntimeError(f"ai_schema_missing_fields: {','.join(missing_schema_fields)}")
        try:
            schema_confidence = float(data.get("confidence"))
        except (TypeError, ValueError):
            raise RuntimeError("ai_schema_invalid_confidence")
        if not 0 <= schema_confidence <= 1:
            raise RuntimeError("ai_schema_confidence_out_of_range")
        if not isinstance(data.get("evidence"), dict):
            raise RuntimeError("ai_schema_invalid_evidence")
        if data.get("episode_numbering_mode") not in {"absolute", "season_episode", "unknown"}:
            raise RuntimeError("ai_schema_invalid_episode_numbering_mode")

        # ── v1.0.0 弹性审计分流 ─────────────────────────────────────
        _confidence = _classify_result(data)

        if _confidence in ("REPAIR", "FAIL"):
            # Fail-Fast：REPAIR/FAIL 不进入后续 TMDB 与入库链路，阻断低置信命中
            raise RuntimeError(f"ai_semantic_fail_fast: confidence={_confidence}")
        # _confidence == "PASS": 直接继续第五步，无需任何处理
        
        # ── 第五步：提取并规范化数据 ────────────────────────────────
        query = (data.get("query") or data.get("clean_name") or cleaned_name or "").strip()
        year = (data.get("year") or "").strip()
        if not isinstance(year, str):
            year = str(year) if year else ""

        # 物理剥离 query 中残留的年份、路径分隔符、垃圾后缀
        query = re.sub(r"\b(19|20)\d{2}\b", "", query).strip()  # 去年份
        query = re.sub(r'[/\\]', ' ', query).strip()            # 去路径斜杠
        query = re.sub(r'\s{2,}', ' ', query).strip()           # 去多余空格

        # ── 字段完整性校验 ────────────────────────────────────────────
        if not data.get("year") and year:
            logger.debug(f"[AI][FIELD] year 字段缺失，已从数据中提取: '{year}'")
        if not data.get("type"):
            logger.warning(f"[AI][FIELD] type 字段缺失，将使用 type_hint='{type_hint}' 兜底")
        if data.get("type") == "tv" and data.get("season") is None:
            logger.warning(f"[AI][FIELD] 剧集 season 字段缺失，将默认为 1 | query='{query}'")
        if data.get("type") == "tv" and data.get("episode") is None:
            logger.debug(f"[AI][FIELD] 剧集 episode 字段缺失 | query='{query}'")

        # ── 幻觉纠偏：AI 返回非标准 type 值时强制映射 ────────────────
        # 支持的幻觉词：film/films/movies -> movie；series/show/shows/anime -> tv
        _MOVIE_ALIASES = {"film", "films", "movies"}
        _TV_ALIASES    = {"series", "show", "shows", "anime", "drama"}
        _VALID_TYPES   = {"movie", "tv", "IGNORE"}

        raw_type = (data.get("type") or "").strip().lower()
        if raw_type in _MOVIE_ALIASES:
            media_type = "movie"
            logger.warning(f"[AI][HALLUCINATION] type='{raw_type}' 已被纠偏为 'movie'")
        elif raw_type in _TV_ALIASES:
            media_type = "tv"
            logger.warning(f"[AI][HALLUCINATION] type='{raw_type}' 已被纠偏为 'tv'")
        elif raw_type == "movie":
            media_type = "movie"
        elif raw_type == "tv":
            media_type = "tv"
        elif raw_type == "ignore":
            media_type = "IGNORE"
        else:
            # 1. mixed 瞬态类型不得使用默认 movie 兜底 -> 2. 交由编排器断路失败 -> 3. 阻断非法 AI 类型污染 TMDB 管线
            fallback = (type_hint or "movie").strip().lower()
            if fallback == "mixed":
                logger.error(f"[AI][MIXED] type='{raw_type}' 无法裁决为 movie/tv，触发瞬态断路")
                raise RuntimeError(f"ai_mixed_type_invalid: {raw_type}")
            # 完全无法识别时，使用调用方传入的 type_hint 兜底
            media_type = fallback if fallback in {"movie", "tv"} else "movie"
            logger.warning(
                f"[AI][FALLBACK] type='{raw_type}' 无法识别，降级为 type_hint='{media_type}'"
            )

        logger.info(
            f"[AIAgent] AI 归档专家识别完成 -> "
            f"query='{query}', filename_year='{(data.get('filename_year') or '').strip()[:4]}', "
            f"knowledge_year='{(data.get('knowledge_year') or '').strip()[:4]}', type='{media_type}'"
        )

        return {
            "query":          query or (raw_filename or cleaned_name or "").strip(),
            "type":           media_type,
            "season":         data.get("season"),
            "episode":        data.get("episode"),
            "filename_year":  (data.get("filename_year") or "").strip()[:4],
            "knowledge_year": (data.get("knowledge_year") or "").strip()[:4],
            "confidence": schema_confidence,
            "evidence": data.get("evidence"),
            "episode_numbering_mode": data.get("episode_numbering_mode"),
            "needs_review": bool(data.get("needs_review", False)),
        }
