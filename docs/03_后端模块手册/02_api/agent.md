# AI 对话端点手册 - `app/api/v1/endpoints/agent.py`

> 路径：`backend/app/api/v1/endpoints/agent.py`
> 路由前缀：`/api/v1/agent`

---

## 一、模块概述

AI 对话网关，接收前端消息，调用 `AIAgent` 完成意图识别，并根据意图码自动触发对应任务。

---

## 二、接口

### `POST /agent/chat`

**请求体：** `ChatRequest`
```json
{ "message": "帮我下载星际穿越" }
```

**响应体：** `ChatResponse`
```json
{ "response": "正在为你寻找资源...", "action": "DOWNLOAD" }
```

---

## 三、处理流程

```
POST /agent/chat
  └─► _get_agent()                          # 模块级单例，跨请求保留对话状态
  └─► AIAgent.process_message(message)
        └─► 返回 (response_text, action_code)
  └─► 根据 action_code 自动触发后台任务：
        ACTION_SCAN     → trigger_scan()
        ACTION_SCRAPE   → trigger_scrape_all()
        ACTION_SUBTITLE → trigger_find_subtitles()
        DOWNLOAD        → 已在 AIAgent 内部处理（ServarrClient）
        None            → 候选展示阶段，不触发任何任务
  └─► 返回 ChatResponse
```

---

## 四、意图码说明

| 意图码 | 触发动作 | 说明 |
|---|---|---|
| `ACTION_SCAN` | `trigger_scan()` | 触发物理扫描 |
| `ACTION_SCRAPE` | `trigger_scrape_all()` | 触发全量刮削 |
| `ACTION_SUBTITLE` | `trigger_find_subtitles()` | 触发字幕查找 |
| `DOWNLOAD` | 无（AIAgent 内部处理）| 寻猎者引擎已在 agent 内部完成 |
| `None` | 无 | 纯对话或候选展示阶段，不触发任何任务 |

---

## 五、单例设计

```python
_agent_instance: AIAgent | None = None

def _get_agent() -> AIAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AIAgent(get_db_manager())
    return _agent_instance
```

- 模块级单例，保证同一进程内 `AIAgent` 只创建一次
- 候选状态（`_pending_candidates`）存储于数据库，`--reload` 模式下模块重载也不会丢失
- 不再每次请求 `AIAgent(db)` 重新实例化

---

## 六、注意事项

- `process_message` 是 `async` 协程，必须 `await` 调用
- 任务触发通过 FastAPI `BackgroundTasks` 实现，不阻塞响应
- 内部导入 `trigger_*` 函数（`from .tasks import ...`）避免循环引用
- 路由受全局 JWT 鉴权保护（在 `main.py` 的 `api_router` 中统一注入）
- 候选展示时 `action_code=None`，endpoint 不打印 `[AI-EXEC]` 追猎引擎日志

---

*最后更新：2026-03-11*
