# agent — AI 对话端点

**文件路径**: `backend/app/api/v1/endpoints/agent.py`  
**路由前缀**: `/api/v1/agent`  
**JWT 保护**: ✅

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/v1/agent/chat` | 发送消息，获取 AI 响应及意图指令 |

---

## POST /agent/chat

### 请求体

```json
{ "message": "帮我扫描一下新文件" }
```

### 响应体

```json
{
  "response": "收到，正在启动物理扫描任务...",
  "action": "ACTION_SCAN"
}
```

### action 意图代码

| 值 | 触发行为 |
|----|----------|
| `ACTION_SCAN` | 自动触发 `POST /tasks/scan` |
| `ACTION_SCRAPE` | 自动触发 `POST /tasks/scrape_all` |
| `ACTION_SUBTITLE` | 自动触发 `POST /tasks/find_subtitles` |
| `DOWNLOAD` | Agent 内部已完成下载请求下发，无需额外操作 |
| `null` | 纯对话，不触发任何任务 |

---

## 模块级单例设计

```python
_agent_instance: AIAgent | None = None

def _get_agent() -> AIAgent:
    global _agent_instance
    if _agent_instance is None:
        _agent_instance = AIAgent(get_db_manager())
    return _agent_instance
```

`AIAgent` 实例在模块级保持单例，确保对话状态跨请求存活。  
`_pending_candidates`（候选列表状态）已持久化到数据库，`--reload` 重启不丢失。

---

## 自动意图触发

```python
if action_code == "ACTION_SCAN":
    await trigger_scan(background_tasks)
elif action_code == "ACTION_SCRAPE":
    await trigger_scrape_all(background_tasks)
elif action_code == "ACTION_SUBTITLE":
    await trigger_find_subtitles(background_tasks)
```

端点内部直接调用任务路由函数，通过 `BackgroundTasks` 异步执行，不阻塞对话响应。

---

## 依赖关系

```
agent.py (端点)
  └── services/ai/agent.py (AIAgent)
        ├── services/ai/llm_client.py (LLMClient)
        ├── services/metadata/adapters.py (TMDBAdapter)
        ├── services/downloader/servarr.py (ServarrClient)
        └── infra/database (db_manager)
```

→ 详见 [04_services/ai.md](../04_services/ai.md)
