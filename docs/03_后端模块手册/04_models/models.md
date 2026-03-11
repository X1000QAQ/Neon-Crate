# 领域模型手册 - `app/models/`

> 路径：`backend/app/models/domain_media.py` + `domain_system.py`

---

## 一、媒体领域模型 (`domain_media.py`)

### `StatsResponse`

```python
class StatsResponse(BaseModel):
    movies: int = 0      # 电影数量（物理文件夹计数）
    tv_shows: int = 0    # 剧集总集数（递归统计视频文件数）
    pending: int = 0     # 待处理任务数
    completed: int = 0   # 已完成任务数
```

### `ScanResponse`

```python
class ScanResponse(BaseModel):
    message: str
    task_id: Optional[str] = None
```

---

## 二、系统领域模型 (`domain_system.py`)

### `SystemSettings`

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `ui_lang` | str | `"zh"` | 界面语言 |
| `min_size_mb` | int | `50` | 最小文件大小（MB）|
| `filename_clean_regex` | str | `""` | 正则清洗规则（15条默认，启动时注入）|
| `cron_enabled` | bool | `False` | 自动扫描开关 |
| `cron_interval_min` | int | `60` | 自动扫描间隔（分钟）|
| `auto_scrape` | bool | `False` | 扫描后自动刮削 |
| `auto_subtitles` | bool | `False` | 刮削后自动找字幕 |
| `tmdb_api_key` | str | `""` | TMDB API Key（加密存储）|
| `os_api_key` | str | `""` | OpenSubtitles Key（加密）|
| `radarr_url` | str | `""` | Radarr 地址 |
| `radarr_api_key` | str | `""` | Radarr Key（加密）|
| `sonarr_url` | str | `""` | Sonarr 地址 |
| `sonarr_api_key` | str | `""` | Sonarr Key（加密）|
| `llm_provider` | str | `"cloud"` | LLM 提供商（cloud/local）|
| `llm_cloud_url` | str | `""` | 云端 LLM API URL |
| `llm_cloud_key` | str | `""` | 云端 LLM Key（加密）|
| `llm_cloud_model` | str | `""` | 云端模型名称 |
| `llm_local_url` | str | `""` | 本地 LLM URL（Ollama）|
| `llm_local_key` | str | `""` | 本地 LLM Key（加密）|
| `llm_local_model` | str | `""` | 本地模型名称 |
| `ai_name` | str | `""` | AI 助手名称 |
| `ai_persona` | str | `""` | AI 人格设定（System Prompt）|
| `expert_archive_rules` | str | `""` | 归档专家规则（JSON 输出约束）|
| `master_router_rules` | str | `""` | 总控路由规则（意图识别 JSON 指令）|

### `PathConfig`

```python
class PathConfig(BaseModel):
    id: Optional[int] = None
    type: str      # "download" 或 "library"
    path: str
    category: str  # "movie" / "tv" / "mixed"，默认 "mixed"
    enabled: bool  # 默认 True
```

### `SettingsConfig`

```python
class SettingsConfig(BaseModel):
    settings: SystemSettings
    paths: List[PathConfig] = []
```

---

## 三、鉴权相关模型

| 模型 | 用途 |
|---|---|
| `AuthStatusResponse` | `GET /auth/status` 响应 |
| `TokenResponse` | `POST /auth/login` 响应（含 JWT）|
| `LoginRequest` | `POST /auth/login` 请求体 |
| `InitRequest` | `POST /auth/init` 请求体（username ≥3字符，password ≥6字符）|
| `DeleteBatchRequest` | `POST /tasks/delete_batch` 请求体 |
| `PurgeRequest` | `POST /tasks/purge` 请求体 |
| `ResetSettingsRequest` | `POST /tasks/settings/reset` 请求体 |
| `ChatRequest` / `ChatResponse` | AI 对话请求/响应 |

---

## 四、重构变更（2026-03-11）

- `StatsResponse.tv_shows`：从「剧集文件夹计数」改为「递归统计视频文件总数」，中英文标签同步更新为「剧集总集数 / Total TV Episodes」
- `SystemSettings.filename_clean_regex`：启动时由 `_inject_ai_defaults()` 注入 15 条默认规则（空时注入，不覆盖用户已有内容）

---

*最后更新：2026-03-11*
