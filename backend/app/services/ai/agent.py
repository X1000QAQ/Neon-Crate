"""
AI Agent 核心模块 - 智能对话与意图识别引擎

功能：
1. 自然语言对话处理
2. 意图识别与指令路由
3. 系统状态查询与反馈
4. 双引擎 LLM 支持（云端 API / 本地 Ollama）
5. 智能媒体名称清洗与搜索优化
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
    """AI 智能助手 - 负责对话处理和意图识别"""
    
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
        初始化 AI Agent (V11 寻猎者完全体)
        
        Args:
            db_manager: DatabaseManager 实例，用于访问配置和数据
        """
        self.db = db_manager
        self.llm_client = LLMClient(db_manager)
        # 候选等待状态：key=会话标识(固定"default"), value={candidates, query, media_type}
        logger.info("✅ [AIAgent] AI 助手已初始化 (V11 寻猎者引擎已装载)")
    
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
    
    async def process_message(self, user_message: str) -> Tuple[str, Optional[str]]:
        """
        处理用户消息的核心方法（总控中枢神经接通版）
        
        🧠 设计理念：
        - 抛弃硬编码关键词匹配，完全依赖大模型的智能理解
        - 动态读取用户配置的 AI 规则，实现真正的可定制化
        - 保留规则引擎作为兜底防线（Fallback）
        
        🔄 处理流程：
        1. 候选等待拦截：若上一轮展示了候选列表，优先匹配用户选择
        2. 动态读取配置：获取 master_router_rules（总控规则）和 ai_persona（AI 人格）
        3. LLM 意图识别：调用大模型进行智能意图识别
        4. 意图路由：根据识别结果路由到对应的处理逻辑
        5. 兜底防线：LLM 失败时使用规则引擎识别意图
        
        🎯 支持的意图：
        - ACTION_SCAN：物理扫描
        - ACTION_SCRAPE：全量刮削
        - ACTION_SUBTITLE：字幕补全
        - SYSTEM_STATUS：系统状态查询
        - DOWNLOAD：下载影片（V11 寻猎者引擎）
        - LOCAL_SEARCH：本地搜索
        - CHAT：普通闲聊
        
        Args:
            user_message: 用户输入的消息
            
        Returns:
            Tuple[str, Optional[str]]: (AI回复文本, 意图指令代码)
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
            # 尝试解析用户输入的序号（1-9）或直接匹配片名
            chosen = None
            stripped = user_message.strip()
            logger.info(f"[AIAgent] 候选匹配尝试: user_input={repr(stripped)}, candidates={[c['title'] for c in candidates]}")
            if stripped.isdigit():
                idx = int(stripped) - 1
                if 0 <= idx < len(candidates):
                    chosen = candidates[idx]
            else:
                # 模糊匹配：支持「片名 (年份)」、「片名」、「序号. 片名」等格式
                # 先尝试提取序号（如「1. 绿巨人浩克」）
                import re as _re_match
                seq_match = _re_match.match(r'^(\d+)[.、。]\s*', stripped)
                if seq_match:
                    idx = int(seq_match.group(1)) - 1
                    if 0 <= idx < len(candidates):
                        chosen = candidates[idx]
                if not chosen:
                    # 去掉年份括号再匹配
                    stripped_clean = _re_match.sub(r'\s*[\(（]\d{4}[\)）]\s*', '', stripped).strip()
                    for c in candidates:
                        title_clean = _re_match.sub(r'\s*[\(（]\d{4}[\)）]\s*', '', c["title"]).strip()
                        # 精确匹配优先：去年份后完全相同
                        if stripped_clean == title_clean:
                            chosen = c
                            break
                    if not chosen:
                        # 次级匹配：原始输入包含片名（而不是片名包含输入，避免「蜘蛛侠」误匹配「蜘蛛侠：纵横宇宙」）
                        for c in candidates:
                            title_clean = _re_match.sub(r'\s*[\(（]\d{4}[\)）]\s*', '', c["title"]).strip()
                            if (stripped == c["title"] or
                                    stripped_clean == title_clean or
                                    (len(title_clean) >= 4 and title_clean in stripped_clean and stripped_clean != title_clean)):
                                chosen = c
                                break
            if chosen:
                # 清除候选状态（数据库）
                self.db.set_config("_pending_candidates", "")
                logger.info(f"[AIAgent] 用户选择候选: {chosen['title']} ({chosen['year']})")
                # 直接用选定结果下载
                from app.services.downloader import ServarrClient
                servarr = ServarrClient(self.db)
                media_type = chosen.get("media_type", "movie")
                tmdb_id = chosen.get("id", 0) or 0
                if media_type == "tv":
                    result = await servarr.add_series(chosen["title"], chosen.get("year", ""), tmdb_id=tmdb_id)
                else:
                    result = await servarr.add_movie(chosen["title"], chosen.get("year", ""), tmdb_id=tmdb_id)
                if result["success"]:
                    title = result["data"].get("title", chosen["title"])
                    return f"已将「{title}」加入下载队列，Radarr/Sonarr 将自动抓取最佳资源。", self.DOWNLOAD
                elif result.get("data", {}).get("status") == "exists":
                    title = result.get("data", {}).get("title", chosen["title"])
                    return f"「{title}」已在下载列表中，无需重复添加。", None
                else:
                    return f"下载任务下发失败：{result['msg']}，请检查 Radarr/Sonarr 配置。", None
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
                intent_res = await self.llm_client.call_llm(
                    system_content,
                    f"指令串: {user_message}"
                )
                intent_data = self._parse_json_response(intent_res)

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
                    response_text = await self._generate_llm_response(user_message, intent_data)

                    # 候选列表展示时不下发 action_code（尚未真正下载）
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
        response_text = await self._generate_llm_response(user_message, intent_data)
        
        # 候选列表展示时不下发 action_code
        if "__CANDIDATES__" in response_text:
            return response_text, None
        # 返回响应文本和意图代码
        action_code = intent if intent != self.CHAT else None
        
        return response_text, action_code
    
    async def _generate_llm_response(self, message: str, intent_data: Dict) -> str:
        """
        使用 LLM 生成智能响应（总控中枢神经接通版）
        
        核心修复：
        1. 所有意图分支都注入 ai_persona（AI 人格），确保响应符合用户设定的人格
        2. 抛弃硬编码响应文本，改为动态调用 LLM 生成个性化回复
        3. 保留系统运行快报，实现全时态感知
        
        Args:
            message: 用户消息
            intent_data: 意图数据
            
        Returns:
            str: AI 响应文本
        """
        intent = intent_data.get("intent")
        
        # 🚀 第一步：动态获取 AI 名称 + 人格设定（复用 property，避免重复读取配置）
        ai_name = self.ai_name
        ai_persona_raw = self.ai_persona
        # 将名字显式注入人格，确保 LLM 知道自己叫什么
        ai_persona = f"你的名字是「{ai_name}」。{ai_persona_raw}" if ai_persona_raw else f"你的名字是「{ai_name}」。"
        
        # 🚀 第二步：全时态感知 - 为所有对话注入系统运行快报
        stats = self._get_system_stats()
        status_summary = f"[实时现状] 总文件:{stats['total']}, 已归档:{stats['archived']}, 磁盘占用:{stats['disk_usage_percent']}%"
        
        if intent in (self.ACTION_SCAN, self.ACTION_SCRAPE, self.ACTION_SUBTITLE):
            # 技术动作：零 Token，本地模板直接返回（process_message 已处理，此处作为 fallback 兜底）
            _ACTION_TEMPLATES = {
                self.ACTION_SCAN:     "好的，物理扫描已启动，稍后刷新页面查看新增文件。",
                self.ACTION_SCRAPE:   "收到，全量刮削任务已下发，刮削完成后媒体信息将自动更新。",
                self.ACTION_SUBTITLE: "明白，字幕补全任务已启动，将为缺失字幕的文件重新检索。",
            }
            return _ACTION_TEMPLATES.get(intent, "收到，任务已启动。")
        
        elif intent == self.SYSTEM_STATUS:
            # ==========================================
            # 📊 系统状态查询（全时态感知）
            # ==========================================
            # 设计目标：提供实时、准确的系统运行状态
            # 
            # 数据来源：
            # 1. 数据库统计：tasks 表 + media_archive 表
            # 2. 系统日志：最近 30 行日志
            # 3. 磁盘占用：真实的磁盘使用率
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
            
            # 第二步：读取真实日志
            log_content = self._read_recent_logs(30)
            
            # 第三步：构建【实时系统快报】（强制约束 LLM 使用真实数据）
            context_report = f"""【实时系统快报 - 绝对禁止编造数据】

数据库总任务数：{stats['total']} 个
🟢 已成功入库 (archived)：{stats['archived']} 个
📦 已刮削 (scraped)：{stats['scraped']} 个
⏳ 待处理队列 (pending)：{stats['pending']} 个
❌ 匹配/处理失败 (failed)：{stats['failed']} 个
⚪ 已跳过重复项 (ignored)：{ignored_count} 个
💾 磁盘占用率：{stats['disk_usage_percent']}%

【最近成功入库的影视（最多 10 条）】
{self._format_recent_tasks(recent)}

【最近系统日志（最后 30 行）】
{log_content}
"""
            
            # 第四步：融合 AI 人格 + 真理宣言 + 实时快报
            full_system_prompt = f"""{ai_persona}

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
            ai_response = await self.llm_client.call_llm(full_system_prompt, message)
            return ai_response
        
        elif intent == self.DOWNLOAD:
            # ==========================================
            # 🚀 V11 寻猎者引擎（Hunter Engine）
            # ==========================================
            # 设计目标：智能下载影片，支持模糊意图和精确匹配
            # 
            # 核心流程：
            # 1. 从 LLM 返回的 JSON 中提取结构化数据（片名、类型、年份）
            # 2. 序号补全：修复 LLM 常把「美国队长1」的「1」丢掉的问题
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
            # 序号补全机制：
            # - 问题：LLM 常把「美国队长1」识别为「美国队长」
            # - 解决：从原始消息提取末尾序号（中文或阿拉伯数字）
            # - 支持：「第一部」「第二部」「1」「2」等格式
            # ==========================================
            # 1. 从 intent_data 中提取结构化数据
            clean_name = intent_data.get("clean_name", "").strip()
            en_name = intent_data.get("en_name", "").strip()  # 80B 提供的英文名，优先用于 TMDB 搜索
            media_type = intent_data.get("type", "movie").strip().lower()
            year = intent_data.get("year", "").strip()
            # TMDB 搜索优先用英文名（准确），无英文名时用中文名
            search_name = en_name if en_name else clean_name

            # 🚀 序号补全修复：LLM 常把「美国队长1」的「1」丢掉
            # 若 clean_name 不含序号，但原始消息末尾有数字，则补回去
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

            # 2.5 模糊意图处理：无年份且无序号时，先查候选列表让用户选择
            import re as _re2
            has_seq = bool(_re2.search(r'\d', clean_name))
            # 使用搜索名（英文名优先）查候选，无年份且无序号时触发
            _candidate_query = en_name if en_name else clean_name
            if not year and not has_seq:
                candidates = await self._tmdb_search_candidates(_candidate_query, media_type)
                if candidates and len(candidates) > 1:
                    logger.info(f"[DOWNLOAD] 模糊意图，返回候选列表: {[c['title'] for c in candidates]}")
                    # 直接本地拼接引导语，不调 LLM，避免 LLM 把候选列表混入 ai_text 造成前端重复显示
                    ai_text = f"找到「{clean_name}」的多个版本，请选择您想要的："
                    # 保存候选状态到数据库（跨请求持久化，不依赖内存单例）
                    _pending_data = {
                        "candidates": candidates,
                        "query": clean_name,
                        "media_type": media_type,
                    }
                    self.db.set_config("_pending_candidates", json.dumps(_pending_data, ensure_ascii=False))
                    logger.info(f"[AIAgent] 候选状态已写入数据库: {len(candidates)} 条, agent_id={id(self)}")
                    # 附加结构化候选数据（前端解析用）
                    quick_opts = [f"{c['title']} ({c['year']})".strip() if c.get('year') else c['title'] for c in candidates]
                    ai_text += f"\n__CANDIDATES__{json.dumps(quick_opts, ensure_ascii=False)}"
                    return ai_text
            
            # 3. 类型归一化处理
            if media_type not in ["movie", "tv"]:
                media_type = "movie"  # 默认为电影
            
            logger.info(f"[DOWNLOAD] 提取意图 -> 片名: {clean_name}, 类型: {media_type}, 年份: {year}")
            
            # 4. 导入下载器并执行
            from app.services.downloader import ServarrClient
            servarr = ServarrClient(self.db)
            
            # 5. 根据类型调用对应的下载方法（优先用英文名搜索 TMDB）
            if media_type == "tv":
                result = await servarr.add_series(search_name, year)
            else:
                result = await servarr.add_movie(search_name, year)
            
            # 6. 生成响应（本地拼接，不再二次调 LLM）
            if result["success"]:
                title = result["data"].get("title", clean_name)
                return f"已将「{title}」加入下载队列，Radarr/Sonarr 将自动抓取最佳资源。"
            elif result.get("data", {}).get("status") == "exists":
                title = result.get("data", {}).get("title", clean_name)
                return f"「{title}」已在下载列表中，无需重复添加。"
            else:
                return f"下载任务下发失败：{result['msg']}，请检查 Radarr/Sonarr 配置或片名是否准确。"
        
        elif intent == self.LOCAL_SEARCH:
            # 本地搜索确认语直接拼接，不调 LLM
            return f"正在本地媒体库中搜索，{status_summary}，请稍候。"
        
        else:  # CHAT
            # 🚀 全时态感知：为普通聊天也注入系统现状
            prompt = f"{ai_persona}\n\n当前系统状态：{status_summary}\n\n执行专业闲聊回复。"
            response = await self.llm_client.call_llm(prompt, message)
            return response

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
            if media_type == "tv":
                results = tmdb.search_tv(name, year if year else None)
            else:
                results = tmdb.search_movie(name, year if year else None)
            # 按 popularity 降序排序（热度高的优先）
            results.sort(key=lambda r: r.get("popularity", 0), reverse=True)
            candidates = []
            for r in results[:5]:
                title = r.get("title") or r.get("name", "")
                rd = r.get("release_date") or r.get("first_air_date") or ""
                yr = rd[:4] if rd else ""
                candidates.append({"title": title, "year": yr, "id": r.get("id"), "popularity": round(r.get("popularity", 0), 1), "media_type": media_type})
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
        
        # 下载意图检测（V11 寻猎者增强版）
        download_keywords = ["下载", "想看", "找片", "搜索", "download"]
        if any(kw in msg_lower for kw in download_keywords):
            # 提取片名和类型
            media_name = self._extract_media_name(message)
            media_type = self._detect_media_type(message)
            year = self._extract_year(message)
            
            # 🚀 V11 关键修复：统一使用 clean_name 键名
            return {
                "intent": self.DOWNLOAD,
                "clean_name": media_name,  # 统一键名
                "type": media_type,
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
        3. shutil.disk_usage：真实磁盘占用率

        Returns:
            Dict: 包含 total, archived, pending, failed, disk_usage_percent
        """
        import shutil
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

            # ── 第三步：获取真实磁盘占用率 ──
            try:
                disk_stat = shutil.disk_usage("/")
                disk_usage_percent = round((disk_stat.used / disk_stat.total) * 100, 2)
            except Exception as disk_err:
                logger.warning(f"[AIAgent] 磁盘占用率获取失败，降级到 cwd: {disk_err}")
                import os
                disk_stat = shutil.disk_usage(os.getcwd())
                disk_usage_percent = round((disk_stat.used / disk_stat.total) * 100, 2)

            return {
                "total": total,
                "scraped": scraped,
                "archived": archived,
                "pending": pending,
                "failed": failed,
                "disk_usage_percent": disk_usage_percent,
            }
        except Exception as e:
            logger.error(f"[AIAgent] 获取统计数据失败: {e}")
            return {
                "total": 0,
                "scraped": 0,
                "archived": 0,
                "pending": 0,
                "failed": 0,
                "disk_usage_percent": 0.0,
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
        self, cleaned_name: str, full_path: str, type_hint: str
    ) -> Optional[Dict]:
        """
        🧠 AI 归档专家 - 智能影视文件识别引擎
        
        设计目标：
        - 将杂乱的影视文件路径清洗为标准的结构化数据
        - 提取片名、年份、类型等关键信息
        - 为 TMDB 搜索提供精准的查询词
        
        核心优势：
        1. 动态规则：从数据库读取 expert_archive_rules，用户可自定义
        2. 路径智能：利用父目录名作为强信号（通常即为作品名）
        3. 幻觉纠偏：自动修正 LLM 返回的非标准类型值
        4. 降级保护：解析失败时使用正则清洗名保底
        
        识别策略：
        1. 优先使用父目录名（如 /tv/Breaking Bad/Season 1/S01E01.mkv → Breaking Bad）
        2. 剧集识别：query 只输出剧名，不含单集标题
        3. 年份提取：只使用文件名中明确出现的年份，不推断
        4. 类型映射：film/films/movies → movie；series/show/anime → tv
        
        Args:
            cleaned_name: 正则清洗后的文件名
            full_path: 完整文件路径
            type_hint: 类型提示（movie/tv）
            
        Returns:
            Optional[Dict]: {
                "query": str,           # TMDB 搜索词（纯净片名）
                "year": str,            # 年份（4位数字或空）
                "chinese_title": str,   # 中文译名（可选）
                "type": str             # 类型（movie/tv/IGNORE）
            }
        """
        # 🚀 第一步：动态获取用户的归档专家规则（DEFAULT_CONFIG 提供钢铁兜底，绝不为空）
        expert_rules = self.db.get_agent_config("expert_archive_rules", "")
        
        # 🚀 第二步：从完整路径提取父目录名作为额外线索
        # 例：'/download/tv/The Boys/Season 03/The.Boys.S03E01.mkv' → 'The Boys'
        parent_dir_hint = ""
        try:
            import os as _os
            parts = full_path.replace("\\", "/").split("/")
            # 取文件名的上级目录，过滤掉 Season xx 这类无意义目录
            for part in reversed(parts[:-1]):
                part = part.strip()
                if part and not re.match(r'^[Ss]eason\s*\d+$', part, re.IGNORECASE):
                    parent_dir_hint = part
                    break
        except Exception:
            pass

        # 🚀 第三步：调用底层 LLM 客户端（确保 JSON 强制输出）
        raw = await self.llm_client.call_llm(
            system_prompt=expert_rules,
            user_prompt=(
                f"请分析以下影视文件：\n"
                f"文件路径: {full_path}\n"
                f"父目录名（强信号，通常即为作品名）: {parent_dir_hint}\n"
                f"清洗后文件名: {cleaned_name}\n"
                f"类型提示: {type_hint or 'movie'}\n\n"
                f"⚠️ 重要约束：\n"
                f"1. 优先以【父目录名】作为作品英文原名的参考依据\n"
                f"2. query 只能是作品官方英文原名，禁止包含集标题、分辨率、编码格式\n"
                f"3. 对于剧集，query 只输出剧名本身（如 'The Boys'），不含当集标题（如 'The Payback'）\n"
                f"4. year 字段：只能填写文件名或路径中明确出现的年份数字，禁止用你的知识推断播出年份，如果没有年份信息就返回空字符串\n"
                f"5. 严禁发散联想，query 必须严格来自文件名或路径中出现的词汇，不可凭空创造\n"
                f"请严格按照 System 设定的 JSON 契约输出。"
            )
        )
        
        # 🚀 第四步：解析 LLM 返回的 JSON（剔除 ```json ... ``` 包裹符号）
        data = self._parse_json_response(raw)
        
        # 降级保护：如果解析失败，使用调用方传入的正则清洗名（cleaned_name）保底
        # cleaned_name 优先级 > AI 提取的 query（AI 已失效），确保搜索词是最干净的
        if not data:
            _fallback_query = (cleaned_name or "").strip()
            logger.warning(
                f"[AI][FALLBACK] JSON 解析失败，降级使用正则清洗名='{_fallback_query}' "
                f"| 原始响应前 200 字符: {raw[:200]}"
            )
            return {
                "query": _fallback_query,
                "year": "",
                "chinese_title": "",
                "type": (type_hint or "movie").strip().lower() or "movie",
            }
        
        # ── 第五步：提取并规范化数据 ────────────────────────────────
        query = (data.get("query") or data.get("clean_name") or cleaned_name or "").strip()
        year = (data.get("year") or "").strip()
        if not isinstance(year, str):
            year = str(year) if year else ""

        # 物理剥离 query 中残留的年份、路径分隔符、垃圾后缀
        query = re.sub(r"\b(19|20)\d{2}\b", "", query).strip()  # 去年份
        query = re.sub(r'[/\\]', ' ', query).strip()            # 去路径斜杠
        query = re.sub(r'\s{2,}', ' ', query).strip()           # 去多余空格

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
            # 完全无法识别时，使用调用方传入的 type_hint 兜底
            fallback = (type_hint or "movie").strip().lower()
            media_type = fallback if fallback in {"movie", "tv"} else "movie"
            logger.warning(
                f"[AI][FALLBACK] type='{raw_type}' 无法识别，降级为 type_hint='{media_type}'"
            )

        logger.info(
            f"[AIAgent] AI 归档专家识别完成 -> "
            f"query='{query}', year='{year}', type='{media_type}'"
        )

        return {
            "query": query or (cleaned_name or "").strip(),
            "year": year[:4] if len(year) >= 4 else year,
            "chinese_title": (data.get("chinese_title") or "").strip(),
            "type": media_type,
        }
