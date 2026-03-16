"""
LLM 客户端 - 双引擎支持（云端 API + 本地 Ollama）

功能：
1. 云端 API 支持（OpenAI/DeepSeek 兼容接口）
2. 本地 Ollama 支持
3. 自动重试机制
4. 统一的调用接口
5. 协议校验层：force_json 参数强制结构化输出
6. V2.0 三阶自愈调度：asyncio 非阻塞超时 + 状态感知级联退避 + 血缘溯源
"""
import time
import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

# ── V2.0 参数对齐表 ────────────────────────────────────────────────
_LOCAL_ASYNCIO_TIMEOUT = 30.0   # asyncio.wait_for 外层熔断（本地）
_CLOUD_ASYNCIO_TIMEOUT = 20.0   # asyncio.wait_for 外层熔断（云端）
_LOCAL_HTTPX_TIMEOUT   = 45.0   # httpx 传输层超时（1.5x asyncio，确保不先于外层断开）
_CLOUD_HTTPX_TIMEOUT   = 30.0   # httpx 传输层超时（1.5x asyncio）


class LLMClient:
    """LLM 客户端 - 统一的 LLM 调用接口（V2.0 三阶自愈版）"""

    def __init__(self, db_manager):
        """
        初始化 LLM 客户端

        Args:
            db_manager: DatabaseManager 实例，用于读取配置
        """
        self.db = db_manager
        # V2.0 血缘溯源：记录最近一次调用的引擎信息
        self.last_engine_info: dict = {}
        logger.info("✅ [LLM] 客户端已初始化 (V2.0 三阶自愈引擎)")

    # ══════════════════════════════════════════════════════════════
    # 内部方法：单引擎请求执行协程（可被 asyncio.wait_for 取消）
    # ══════════════════════════════════════════════════════════════

    async def _call_provider(
        self,
        api_url: str,
        headers: dict,
        payload: dict,
        httpx_timeout: float,
        retries: int,
    ) -> str:
        """
        向单个 LLM 端点发起请求（带重试）。

        此方法为纯 I/O 协程，可被外层 asyncio.wait_for 取消，
        取消时 httpx 连接自动关闭，不会产生资源泄露。

        Args:
            api_url:       端点 URL
            headers:       请求头（含 Authorization）
            payload:       请求体
            httpx_timeout: httpx 传输层超时（秒）
            retries:       重试次数

        Returns:
            str: LLM 响应内容

        Raises:
            RuntimeError: 所有重试耗尽后抛出
        """
        # 🛡️ 网络防火墙：强制 timeout 最小值为 15s，最大值为 120s
        httpx_timeout = max(15.0, min(httpx_timeout, 120.0))
        
        for attempt in range(max(retries, 1)):
            try:
                async with httpx.AsyncClient(follow_redirects=True, timeout=httpx_timeout) as client:
                    resp = await client.post(
                        api_url,
                        headers=headers,
                        json=payload,
                    )
                    # 就地拦截 429 限流，等待策略：10s / 20s / 40s
                    if resp.status_code == 429:
                        wait = 10 * (2 ** attempt)
                        logger.warning(f"[LLM] 限流 (429)，等待 {wait}s 后重试")
                        await asyncio.sleep(wait)
                        continue
                    resp.raise_for_status()
                    return resp.json()['choices'][0]['message']['content'].strip()
            except Exception as e:
                logger.warning(
                    f"⚠️ [LLM] 通讯波动 (第 {attempt + 1}/{retries} 次): {e}"
                )
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                else:
                    logger.error(f"❌ [LLM] 所有重试耗尽: {e}", exc_info=True)
                    raise RuntimeError(f"LLM 调用失败: {e}")
        raise RuntimeError("LLM 调用失败: 未知错误")

    # ══════════════════════════════════════════════════════════════
    # 公开方法：统一入口（三阶自愈调度）
    # ══════════════════════════════════════════════════════════════

    async def call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        retries: int = 3,
        temperature: float = 0.1,
        force_json: bool = False,
        prefer_local: bool = False,
    ) -> str:
        """
        调用 LLM 生成响应（V2.0 三阶自愈调度）

        调度逻辑：
          阶段 1：路由决策 — 根据物理开关 + prefer_local 确定首选引擎
          阶段 2：首选引擎执行 — asyncio.wait_for 非阻塞超时包装
          阶段 3：状态感知级联退避 — 首选失败时检查备用引擎可用性后切换

        Args:
            system_prompt: 系统提示词
            user_prompt:   用户提示词
            retries:       重试次数（仅对云端生效；本地固定 1 次）
            temperature:   温度参数
            force_json:    强制 JSON 输出（仅云端注入 response_format）
            prefer_local:  True 时将本次任务卸载至本地边缘模型

        Returns:
            str: LLM 响应文本
        """
        # ── 工具函数：将数据库值转为 bool ─────────────────────────────
        def _to_bool(val, default: bool) -> bool:
            if val is None or val == "":
                return default
            if isinstance(val, bool):
                return val
            return str(val).lower() not in ("false", "0", "no")

        cloud_enabled = _to_bool(self.db.get_config("llm_cloud_enabled", True), True)
        local_enabled = _to_bool(self.db.get_config("llm_local_enabled", False), False)

        if not cloud_enabled and not local_enabled:
            error_msg = "error: 所有 AI 推理引擎均已物理关闭，请在设置中开启至少一个引擎。"
            logger.error(f"❌ [LLM] {error_msg}")
            return error_msg

        # ── 阶段 1：路由决策 ──────────────────────────────────────────
        if cloud_enabled and local_enabled:
            primary_provider  = "local" if prefer_local else "cloud"
            fallback_provider = "cloud" if prefer_local else None
            if prefer_local:
                logger.info("🧠 [LLM-Router] 双擎并联激活：重负载任务已卸载至本地边缘计算")
        elif cloud_enabled:
            primary_provider  = "cloud"
            fallback_provider = None
        else:
            primary_provider  = "local"
            fallback_provider = None

        # ── 构建 payload 工具函数 ────────────────────────────────────
        def _build_payload(provider: str) -> tuple[dict, dict, str, str]:
            """返回 (payload, headers, api_url, model)"""
            _url   = self.db.get_config(f"llm_{provider}_url") or ""
            _key   = self.db.get_config(f"llm_{provider}_key") or ""
            _model = self.db.get_config(f"llm_{provider}_model") or ""
            _is_local = (provider == "local")
            _payload = {
                "model": _model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                "temperature": temperature,
                "enable_thinking": False,  # 关闭 Qwen3 思考模式，避免输出污染 JSON 解析
            }
            if force_json and not _is_local:
                _payload["response_format"] = {"type": "json_object"}
                logger.debug("[LLM] response_format=json_object 已启用")
            _headers = {
                "Authorization": f"Bearer {_key}",
                "Content-Type":  "application/json",
            }
            return _payload, _headers, _url, _model

        # ── 阶段 2：执行首选引擎（asyncio.wait_for 非阻塞包装）────────
        _t0 = time.monotonic()
        primary_payload, primary_headers, primary_url, primary_model = _build_payload(primary_provider)

        if not primary_url:
            # 首选未配置，直接切换至备用
            if fallback_provider:
                logger.warning(f"[LLM] {primary_provider} URL 未配置，直接切换至 {fallback_provider}")
            else:
                error_msg = f"error: 缺失 {primary_provider} URL 配置"
                logger.error(f"❌ [LLM] {error_msg}")
                return error_msg
        else:
            is_local_primary = (primary_provider == "local")
            _asyncio_timeout = _LOCAL_ASYNCIO_TIMEOUT if is_local_primary else _CLOUD_ASYNCIO_TIMEOUT
            _httpx_timeout   = _LOCAL_HTTPX_TIMEOUT   if is_local_primary else _CLOUD_HTTPX_TIMEOUT
            _retries         = 1 if is_local_primary else retries

            try:
                result = await asyncio.wait_for(
                    self._call_provider(
                        primary_url, primary_headers, primary_payload,
                        _httpx_timeout, _retries,
                    ),
                    timeout=_asyncio_timeout,
                )
                latency_ms = round((time.monotonic() - _t0) * 1000)
                self.last_engine_info = {
                    "provider":   primary_provider,
                    "model":      primary_model,
                    "fallback":   False,
                    "latency_ms": latency_ms,
                }
                logger.info(
                    f"✅ [LLM] {primary_provider}({primary_model}) 引擎响应成功"
                    f" | 耗时 {latency_ms}ms"
                )
                return result

            except asyncio.TimeoutError:
                logger.warning(
                    f"⏱️ [LLM] {primary_provider} 协程超时（{_asyncio_timeout}s），"
                    f"触发状态感知级联退避"
                )
            except Exception as e:
                logger.warning(f"⚠️ [LLM] {primary_provider} 失败: {e}，触发状态感知级联退避")

        # ── 阶段 3：状态感知级联退避 ──────────────────────────────────
        _fallback = fallback_provider
        if _fallback is None and primary_provider == "local" and cloud_enabled:
            # 单本地模式首选失败，云端开关开启时尝试补位
            _fallback = "cloud"

        if _fallback:
            fb_payload, fb_headers, fb_url, fb_model = _build_payload(_fallback)
            if not fb_url:
                error_msg = f"error: 缺失 {_fallback} URL 配置（降级补位失败）"
                logger.error(f"❌ [LLM] {error_msg}")
                return error_msg

            logger.info(f"⚡ [LLM-Fallback] {_fallback} 可用，激活补位引擎")
            _fb_asyncio = _LOCAL_ASYNCIO_TIMEOUT if _fallback == "local" else _CLOUD_ASYNCIO_TIMEOUT
            _fb_httpx   = _LOCAL_HTTPX_TIMEOUT   if _fallback == "local" else _CLOUD_HTTPX_TIMEOUT
            _fb_retries = 1 if _fallback == "local" else retries

            try:
                result = await asyncio.wait_for(
                    self._call_provider(
                        fb_url, fb_headers, fb_payload, _fb_httpx, _fb_retries,
                    ),
                    timeout=_fb_asyncio,
                )
                latency_ms = round((time.monotonic() - _t0) * 1000)
                self.last_engine_info = {
                    "provider":   _fallback,
                    "model":      fb_model,
                    "fallback":   True,
                    "latency_ms": latency_ms,
                }
                logger.info(
                    f"✅ [AI-ROUTER] 任务由 {primary_provider} 降级至 {_fallback} 成功"
                    f" | 最终大脑: {fb_model} | 耗时 {latency_ms}ms"
                )
                return result

            except asyncio.TimeoutError:
                logger.error(f"❌ [LLM] 备用引擎 {_fallback} 同样超时，所有引擎均不可用")
            except Exception as e:
                logger.error(f"❌ [LLM] 备用引擎 {_fallback} 失败: {e}")

        # ── 最终兜底：所有引擎均失败，由调用方（agent.py）决定降级策略 ──
        raise RuntimeError("所有 LLM 引擎均不可用，请检查配置或网络连接")
