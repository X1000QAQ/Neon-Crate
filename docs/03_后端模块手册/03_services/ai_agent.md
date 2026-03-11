# AI Agent 服务手册 - `app/services/ai/`

> 路径：`backend/app/services/ai/agent.py` + `llm_client.py`

---

## 一、模块概述

AI 决策调度层，负责：
1. 自然语言意图识别（LLM 主路由 + 规则引擎兜底）
2. 系统指令路由（扫描/刮削/字幕/下载/状态查询）
3. LLM 响应生成（人格注入 + 实时系统状态融合）
4. 媒体文件 AI 识别（归档专家规则 + JSON 输出）

所有配置（`ai_persona`、`master_router_rules`、`expert_archive_rules`、LLM URL/Key/Model）均从数据库动态读取，WebUI 修改后**无需重启**即时生效。

---

## 二、意图常量

| 常量 | 含义 |
|---|---|
| `ACTION_SCAN` | 物理扫描 |
| `ACTION_SCRAPE` | 全量刮削 |
| `ACTION_SUBTITLE` | 字幕查找 |
| `DOWNLOAD` | 下载指令 |
| `LOCAL_SEARCH` | 本地搜索 |
| `SYSTEM_STATUS` | 系统状态查询 |
| `CHAT` | 普通聊天 |

---

## 三、核心方法

### `process_message(user_message) -> (str, Optional[str])`

总控入口，处理流程：
1. 读取 `master_router_rules` 和 `ai_persona`
2. **候选等待拦截**：检查数据库中是否有待确认的候选状态（`_pending_candidates`），若有则优先匹配用户选择，跳过 LLM 意图识别
3. LLM JSON 意图识别
4. 解析失败降级到关键词规则引擎
5. 调用 `_generate_llm_response()` 生成响应
6. 若响应含 `__CANDIDATES__`，强制 `action_code=None`（候选展示阶段不触发下载）
7. 返回 `(响应文本, 意图代码)`

#### 候选等待拦截逻辑

- 候选状态存储于数据库 `config` 表的 `_pending_candidates` 键，JSON 格式
- 跨请求持久化，不依赖内存单例，`--reload` 模式下也不会丢失
- 匹配优先级：
  1. 纯数字（`1`~`9`）→ 按序号取候选
  2. `序号. 片名` 格式（如 `1. 蜘蛛侠`）→ 提取序号
  3. 精确匹配：去年份后完全相同
  4. 次级匹配：候选片名（≥4字）包含在用户输入中
- 匹配成功：清除候选状态，直接调用 `ServarrClient` 下载（携带 TMDB ID 跳过侦察）
- 匹配失败（用户输入无法匹配任何候选）：
  - 若输入**看起来像候选选择**（纯数字、`序号.` 格式、包含候选片名前4字），但精确匹配失败：**保留候选状态**，返回提示 + 重新附加 `__CANDIDATES__` 数据
  - 其余所有输入（聊天、查看日志、查看失败任务、扫描、刮削等任何非选择意图）：一律**清除候选状态**，放行至正常意图识别流程

### `ai_identify_media(cleaned_name, full_path, type_hint) -> Optional[Dict]`

AI 归档专家识别，用于刮削流程：
- 读取 `expert_archive_rules` 作为 System Prompt
- LLM 输出 JSON：`{query, year, chinese_title, type}`
- 幻觉纠偏：`film` → `movie`，`series/show/anime` → `tv`
- 解析失败降级使用 `cleaned_name`

### `_generate_llm_response(message, intent_data) -> str`

| 意图 | 处理逻辑 |
|---|---|
| `ACTION_SCAN/SCRAPE/SUBTITLE` | `asyncio.wait_for(call_llm(...), timeout=30s)`，超时降级本地拼接文本 |
| `SYSTEM_STATUS` | 注入真实数据库统计（`total`、`archived`、`scraped`、`pending`、`failed`、`disk_usage_percent`）+ 日志，防止 LLM 编造数据 |
| `DOWNLOAD`（模糊，无年份无序号）| 调用 `_tmdb_search_candidates()` 返回前5候选，写入 `_pending_candidates`；引导语由本地直接拼接（不调 LLM），保证 `__CANDIDATES__` 标记前的文本是干净的单行引导语 |
| `DOWNLOAD`（精准）| 有年份或序号时直接调用 Servarr 下载，本地拼接结果文本 |
| `LOCAL_SEARCH` | 本地拼接确认语 |
| `CHAT` | 注入系统快报 + 人格，LLM 生成回复 |

### `_tmdb_search_candidates(name, media_type, year="") -> list`

- 调用 TMDB 搜索，按 `popularity` 降序排序
- 返回前 5 条：`[{"title", "year", "id", "popularity", "media_type"}, ...]`
  - 注意：包含 `media_type` 字段，候选拦截下载时使用
- 结果附加到响应末尾：`__CANDIDATES__[...]`（前端解析渲染快捷按钮）
- 同时写入数据库 `_pending_candidates`，等待用户下一轮选择

---

## 四、`LLMClient`

```python
LLMClient(db_manager)  # 配置从 DB 动态读取
```

### `call_llm(system_prompt, user_prompt, retries=3, temperature=0.1) -> str`

- 从 DB 读取 `llm_provider`（cloud/local）、URL、Key、Model
- 三连击指数退避重试（1s → 2s → 4s）
- 兼容所有 OpenAI 格式 API（DeepSeek、Ollama 等）
- payload 加入 `"enable_thinking": False`，关闭 Qwen3 思考模式

---

## 五、数据流

```
POST /agent/chat
  └─► AIAgent.process_message()
        ├─► 读取 DB _pending_candidates     # 候选状态拦截
        │     ├─► 匹配成功 → ServarrClient(tmdb_id)  # 直接下载，跳过 LLM
        │     ├─► 匹配失败（像候选选择）→ 保留状态，返回提示+候选
        │     └─► 匹配失败（其他任何意图）→ 清除状态，放行至意图识别
        ├─► LLMClient.call_llm()            # 意图识别
        ├─► _generate_llm_response()
        │     ├─► _get_system_stats()       # 实时统计
        │     ├─► _read_recent_logs()       # 日志读取
        │     ├─► _tmdb_search_candidates() # 候选查询 + 写入 DB
        │     └─► ServarrClient（精准下载意图）
        ├─► 含 __CANDIDATES__ → action_code=None
        └─► 返回 (text, action_code)
```

---

## 六、注意事项

- `master_router_rules` 为空时自动降级到关键词匹配
- `_read_recent_logs()` 自适应路径探测（优先从 `db_path` 反推 → 向上查找 `backend` 目录 → Docker 固定路径 `/app/data/logs/app.log`），不依赖硬编码绝对路径
- `_generate_llm_response` 系统快报统计字段：`total`、`archived`、`scraped`、`pending`、`failed`、`disk_usage_percent`（不含 `success`）
- DOWNLOAD 序号补全：从原始消息提取末尾数字/中文数字，自动补充到 `clean_name`
- 英文名优先搜索：LLM 同时输出 `en_name`，TMDB 搜索优先使用英文名
- 候选展示时 `action_code=None`，不触发 endpoint 的追猎引擎日志
- 动作意图（SCAN/SCRAPE/SUBTITLE）LLM 调用设 30s 超时，超时降级本地文本，避免小模型卡死前端
- 候选匹配失败判断采用**白名单反转逻辑**：只有输入明确像候选选择（纯数字/序号格式/含候选片名前4字）才保留状态；其余一律清除，避免关键词黑名单覆盖不全的问题

---

*最后更新：2026-03-11*
