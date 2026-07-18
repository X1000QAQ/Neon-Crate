"""
公共 HTTP 工具 - 同步 GET 请求、连接池复用与重试防护

职责：
- 为 TMDB、OpenSubtitles、Radarr / Sonarr 等外部接口提供统一 GET 请求封装。
- 复用模块级 `httpx.Client` 连接池，减少重复 TCP 握手。
- 对 429、5xx、超时和瞬时网络异常执行指数退避重试。

风险提示：
- `http_get_with_retry()` 是元数据、下载和重构链路的共享底座，调用面较广。
- 修改超时、返回值或重试条件会影响多个外部服务调用。
- 本批仅补充注释，不调整任何网络行为。
"""
import time
import threading
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 2.0

# 模块级共享 HTTP 客户端（双重检查锁，连接池复用）
_http_client: Optional[httpx.Client] = None
_client_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    """获取模块级共享 HTTP 客户端（连接池复用，线程安全）"""
    global _http_client
    if _http_client is None:
        with _client_lock:
            if _http_client is None:
                _http_client = httpx.Client(
                    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                    follow_redirects=True,
                )
    return _http_client


def http_get_with_retry(
    url: str,
    params: dict = None,
    timeout: float = 15.0
) -> Optional[httpx.Response]:
    """
    带重试的同步 HTTP GET 请求。

    共享底座：TMDB 元数据、海报 / Fanart 下载、API Key 验证和部分重构搜索都会经过本函数。
    因此返回值、超时裁剪、重试次数和 4xx / 5xx 判定属于跨模块契约，修改前必须评估全链路影响。

    重试策略：
    - 2xx / 3xx：立即返回响应。
    - 非 429 的 4xx：返回响应，由调用方决定如何解释业务错误。
    - 429 / 5xx：按 2s / 4s / 8s 指数退避重试。
    - 超时和瞬时网络异常：按同样节奏重试。
    - 所有重试耗尽后返回 None。

    Args:
        url: 请求 URL。
        params: 查询参数。
        timeout: 超时时间，运行时会被裁剪到 10s～60s。

    Returns:
        Optional[httpx.Response]: 成功或客户端错误时返回响应对象；重试耗尽或异常时返回 None。
    """
    # 🛡️ 网络防火墙：强制 timeout 最小值为 10s，最大值为 60s
    timeout = max(10.0, min(timeout, 60.0))
    client = _get_http_client()

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params or {}, timeout=timeout)

            if resp.is_success or (resp.is_client_error and resp.status_code != 429):
                return resp

            if resp.status_code == 429 or resp.is_server_error:
                wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
                logger.warning(
                    f"[HTTP] 状态码 {resp.status_code}，第 {attempt} 次重试，"
                    f"等待 {wait:.1f}s | {url}"
                )
                time.sleep(wait)
                continue

            logger.error(f"[HTTP] 错误 {resp.status_code}: {url}")
            return None

        except httpx.TimeoutException:
            wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
            logger.warning(f"[HTTP] 超时（第 {attempt} 次），等待 {wait:.1f}s | {url}")
            if attempt < _MAX_RETRIES:
                time.sleep(wait)
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadError) as e:
            # SSL EOF / 连接重置 / 网络瞬断均属瞬时错误，走重试路径
            wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
            logger.warning(f"[HTTP] 网络异常（第 {attempt} 次），等待 {wait:.1f}s: {e}")
            if attempt < _MAX_RETRIES:
                time.sleep(wait)
        except Exception as e:
            logger.error(f"[HTTP] 未预期异常: {e}")
            return None

    logger.error(f"[HTTP] 已重试 {_MAX_RETRIES} 次仍失败: {url}")
    return None
