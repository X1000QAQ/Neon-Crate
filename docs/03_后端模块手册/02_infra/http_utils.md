# http_utils — 公共 HTTP 工具

**文件路径**: `backend/app/infra/http_utils.py`  
**核心函数**: `http_get_with_retry(url, params, timeout) -> Optional[httpx.Response]`

---

## 职责

为所有对外 HTTP GET 请求提供统一的**指数退避重试**机制，调用方无需关心限流和超时处理。

---

## 函数签名

```python
def http_get_with_retry(
    url: str,
    params: dict = None,
    timeout: float = 10.0
) -> Optional[httpx.Response]:
```

**返回值**：成功时返回 `httpx.Response`，失败返回 `None`。

---

## 重试策略

| 参数 | 值 |
|------|----|
| 最大重试次数 | 3 次 |
| 基础等待时间 | 2.0 秒 |
| 退避算法 | `wait = 2.0 × 2^(attempt-1)` |
| 等待序列 | 2s → 4s → 8s |

### 各 HTTP 状态码处理

| 状态码 | 处理方式 |
|--------|----------|
| `200` | 立即返回 Response |
| `429` (限流) | 指数退避后重试 |
| 超时异常 | 固定等待 2s 后重试 |
| 其他错误状态码 | 记录日志，返回 `None` |
| 其他异常 | 记录日志，返回 `None` |

---

## 使用场景

所有以下模块均通过此函数发起 HTTP 请求：

| 调用方 | 用途 |
|--------|------|
| `services/metadata/adapters.py` | TMDB 搜索（电影/剧集/外部ID）|
| `services/metadata/metadata_manager.py` | TMDB 详情 + 海报/Fanart 下载 |

> **注意**：`services/subtitle/engine.py`（OpenSubtitles）和 `services/ai/llm_client.py`（LLM API）使用 `httpx.AsyncClient`，有各自的重试逻辑，不复用此函数。

---

## 示例

```python
from app.infra.http_utils import http_get_with_retry

resp = http_get_with_retry(
    url="https://api.themoviedb.org/3/search/movie",
    params={"api_key": "...", "query": "Dune"},
    timeout=10.0
)
if resp:
    data = resp.json()
else:
    logger.error("请求失败，已重试 3 次")
```
