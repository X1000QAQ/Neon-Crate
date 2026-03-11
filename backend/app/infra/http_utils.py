"""
公共 HTTP 工具 - 带 429 限流重试的 GET 请求
"""
import time
import httpx
from typing import Optional
import logging

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_BASE_WAIT = 2.0


def http_get_with_retry(
    url: str,
    params: dict = None,
    timeout: float = 10.0
) -> Optional[httpx.Response]:
    """
    带 429 重试的同步 HTTP GET 请求
    - 429 限流：指数退避重试
    - 超时：记录警告后重试
    - 其他错误：记录后返回 None
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, params=params or {})
            if resp.status_code == 200:
                return resp
            if resp.status_code == 429:
                wait = _RETRY_BASE_WAIT * (2 ** (attempt - 1))
                logger.warning(f"[HTTP] 限流 (429)，第 {attempt} 次重试，等待 {wait:.1f}s")
                time.sleep(wait)
                continue
            logger.error(f"[HTTP] 错误 {resp.status_code}: {url}")
            return None
        except httpx.TimeoutException:
            logger.warning(f"[HTTP] 超时（第 {attempt} 次）: {url}")
            if attempt < _MAX_RETRIES:
                time.sleep(_RETRY_BASE_WAIT)
        except Exception as e:
            logger.error(f"[HTTP] 异常: {e}")
            return None
    logger.error(f"[HTTP] 已重试 {_MAX_RETRIES} 次仍失败: {url}")
    return None
