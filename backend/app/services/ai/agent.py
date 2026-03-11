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
        self._pending_candidates: dict = {}
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

        策略：
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
        
        核心修复：
        1. 动态读取 master_router_rules（总控中枢规则）和 ai_persona（AI 人格）
        2. 将两者融合为 System Prompt，注入到 80B 智脑
        3. 抛弃硬编码关键词匹配，完全依赖大模型的 JSON 返回值进行意图识别
        4. 保留规则引擎作为兜底防线（Fallback）
        
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
                self._pending_candidates.pop("default", None)
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
                    self._pending_candidates.pop("default", None)
                    # 不 return，继续往下走正常意图识别
        
        # 🚀 第二步：融合 System Prompt（将人格设定作为最高准则，附带总控路由契约）
        system_content = f"{ai_persona}\n\n{router_rules}".strip()
        
        # 🚀 第三步：优先使用 LLM 进行智能意图识别（如果总控规则存在）
        if router_rules.strip():
            try:
                # 调用 80B 智脑，传入完整的 System Prompt
                intent_res = await self.llm_client.call_llm(
                    system_content, 
                    f"指令串: {user_message}"
                )
                intent_data = self._parse_json_response(intent_res)
                
                if intent_data:
                    intent = intent_data.get("intent", self.CHAT)
                    
                    # 动作类意图（SCAN/SCRAPE/SUBTITLE）在 _generate_llm_response
                    # 内部已改为本地拼接，不再二次调用 LLM。
                    # DOWNLOAD/SYSTEM_STATUS/CHAT 仍需 LLM 生成回复。
                    response_text = await self._generate_llm_response(user_message, intent_data)
                    
                    # 候选列表展示时不下发 action_code（尚未真正下载）
                    if "__CANDIDATES__" in response_text:
                        return response_text, None
                    # 返回响应文本和意图代码
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
        
        # 🚀 第一步：动态获取 AI 名称 + 人格设定，融合为完整身份
        ai_name = self.db.get_agent_config("ai_name", "AI 智能助理")
        ai_persona_raw = self.db.get_agent_config("ai_persona", "")
        # 将名字显式注入人格，确保 LLM 知道自己叫什么
        ai_persona = f"你的名字是「{ai_name}」。{ai_persona_raw}" if ai_persona_raw else f"你的名字是「{ai_name}」。"
        
        # 🚀 第二步：全时态感知 - 为所有对话注入系统运行快报
        stats = self._get_system_stats()
        status_summary = f"[实时现状] 总文件:{stats['total']}, 已归档:{stats['archived']}, 磁盘占用:{stats['disk_usage_percent']}%"
        
        if intent in (self.ACTION_SCAN, self.ACTION_SCRAPE, self.ACTION_SUBTITLE):
            # 动作确认语：优先让 LLM 生成个性化回复，但设置硬超时（本地小模型保护）
            # 超时或失败则立即降级为本地文本，保证前端不卡死
            action_labels = {
                self.ACTION_SCAN:     ("物理扫描",   "稍后刷新页面查看新增文件"),
                self.ACTION_SCRAPE:   ("全量刮削",   "刮削完成后媒体信息将自动更新"),
                self.ACTION_SUBTITLE: ("字幕补全",   "将为缺失字幕的文件重新检索"),
            }
            label, hint = action_labels[intent]
            fallback = f"收到，正在启动{label}任务，{status_summary}，{hint}。"
            try:
                prompt = (
                    f"{ai_persona}\n\n当前系统状态：{status_summary}\n\n"
                    f"用户请求启动{label}任务，请用简短的一句话确认并告知即将执行的操作。"
                )
                llm_reply = await asyncio.wait_for(
                    self.llm_client.call_llm(prompt, message),
                    timeout=30.0  # 动作确认语最多等 30s，超时直接用本地文本
                )
                # LLM 返回错误字符串时降级
                if llm_reply and not llm_reply.startswith("error:"):
                    return llm_reply
            except asyncio.TimeoutError:
                logger.warning(f"[AIAgent] {label}确认语 LLM 超时(30s)，已降级为本地文本")
            except Exception as e:
                logger.warning(f"[AIAgent] {label}确认语 LLM 异常，已降级: {e}")
            return fallback
        
        elif intent == self.SYSTEM_STATUS:
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
            # 🚀 V11 寻猎者计划 (总控中枢神经接通版)
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
                    self._pending_candidates["default"] = _pending_data  # 内存同步（单次请求内复用）
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
        
        核心功能：
        1. 动态读取用户配置的 expert_archive_rules（智能影视归档专家规则）
        2. 将完整规则作为 System Prompt 注入到大模型
        3. 让 80B 智脑发挥真正的威力，精准提炼片名、年份、类型
        
        Args:
            cleaned_name: 清洗后的文件名
            full_path: 完整文件路径
            type_hint: 类型提示
            
        Returns:
            Optional[Dict]: 包含 query, year, chinese_title, type 的字典
        """
        # 🚀 第一步：动态获取用户的归档专家规则（默认值已在 db_manager.py 中定义）
        expert_rules = self.db.get_agent_config("expert_archive_rules", "")
        
        # 降级保护：如果规则为空，使用基础兜底逻辑
        if not (expert_rules or "").strip():
            logger.warning("[AIAgent] expert_archive_rules 为空，使用降级方案")
            return {
                "query": (cleaned_name or "").strip(),
                "year": "",
                "chinese_title": "",
                "type": (type_hint or "movie").strip().lower() or "movie",
            }
        
        # 🚀 第二步：调用底层 LLM 客户端（确保 JSON 强制输出）
        raw = await self.llm_client.call_llm(
            system_prompt=expert_rules,
            user_prompt=(
                f"请分析以下影视文件：\n"
                f"文件路径: {full_path}\n"
                f"清洗后文件名: {cleaned_name}\n"
                f"类型提示: {type_hint or 'movie'}\n\n"
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
