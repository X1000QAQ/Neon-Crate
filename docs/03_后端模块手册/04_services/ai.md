# ai — AI 服务层

**目录**: `backend/app/services/ai/`

---

## 模块组成

| 文件 | 类 | 职责 |
|------|----|------|
| `agent.py` | `AIAgent` | 意图识别 + 对话处理 + 下载决策 |
| `llm_client.py` | `LLMClient` | 双引擎 LLM 调用（云端/本地）|

---

## AIAgent

### 初始化

```python
agent = AIAgent(db_manager=db)
```

`ai_name` / `ai_persona` 通过 `@property` 动态读取数据库，热更新无需重启。

### process_message 执行流程

```
1. 读取候选等待状态（db.get_config("_pending_candidates")）
   └── 若有待确认候选列表，优先匹配用户选择（数字序号/片名模糊匹配）

2. 构建 System Prompt = ai_persona + master_router_rules

3. 调用 LLM 意图识别（返回 JSON）
   └── LLM 失败 → 降级 _recognize_intent() 关键词规则引擎

4. _generate_llm_response() 生成最终回复
```

### 意图代码

| 代码 | 触发行为 |
|------|----------|
| `ACTION_SCAN` | 触发物理扫描 |
| `ACTION_SCRAPE` | 触发全量刮削 |
| `ACTION_SUBTITLE` | 触发字幕补完 |
| `DOWNLOAD` | 内部完成 Servarr 下载请求下发 |
| `SYSTEM_STATUS` | 实时读取 DB 数据生成状态汇报 |
| `CHAT` | 普通对话 |

### ai_identify_media

```python
result = await agent.ai_identify_media(
    cleaned_name="Attack on Titan S03E10",
    full_path="/downloads/...",
    type_hint="tv"
)
# 返回
{
    "query": "Attack on Titan",
    "year": "2013",
    "chinese_title": "进击的巨人",
    "type": "tv"
}
```

幻觉纠偏：`film/movies → movie`，`series/anime → tv`，无法识别时降级为 `type_hint`。

### _pending_candidates 持久化

```python
# 写入
self.db.set_config("_pending_candidates", json.dumps(data))
# 读取
raw = self.db.get_config("_pending_candidates", "")
# 清除
self.db.set_config("_pending_candidates", "")
```

状态持久化到数据库，`--reload` 重启后不丢失。

---

## LLMClient

### 初始化

```python
client = LLMClient(db_manager=db)
```

### call_llm

```python
result = await client.call_llm(
    system_prompt="你是...",
    user_prompt="分析这个文件名",
    retries=3,
    temperature=0.1
)
```

### 双引擎配置

| 配置键 | 说明 |
|--------|------|
| `llm_provider` | `"cloud"` 或 `"local"` |
| `llm_cloud_url/key/model` | 云端 API（OpenAI/DeepSeek 兼容）|
| `llm_local_url/key/model` | 本地 Ollama |

### 重试策略

| 参数 | 云端 | 本地 |
|------|------|------|
| timeout | 60s | 180s |
| retries | 3 次 | 1 次（失败直接降级）|
| 退避 | `2^attempt` 秒 | — |

`enable_thinking: false` 关闭 Qwen3 思考模式，防止输出污染 JSON 解析。
