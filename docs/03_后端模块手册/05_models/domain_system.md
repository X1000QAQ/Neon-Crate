# domain_system — 系统领域模型

**文件路径**: `backend/app/models/domain_system.py`

---

## 模型列表

### PathConfig

```python
class PathConfig(BaseModel):
    id: Optional[int] = None
    type: str        # "download" | "library"
    path: str        # 物理路径
    category: str    # "movie" | "tv" | "mixed"
    enabled: bool = True
```

### SystemSettings

系统全量设置，对应前端设置页面的所有配置项。

| 字段 | 类型 | 说明 |
|------|------|------|
| `min_size_mb` | `int ≥ 0` | 扫描最小体积（MB）|
| `filename_clean_regex` | `str` | 多行正则，每行一条过滤规则 |
| `cron_enabled` | `bool` | 定时巡逻总开关 |
| `cron_interval_min` | `int` | 巡逻间隔（分钟）|
| `auto_scrape` | `bool` | 扫描后自动刮削 |
| `auto_subtitles` | `bool` | 刮削后自动搜索字幕 |
| `tmdb_api_key` | `str` | TMDB API Key |
| `os_api_key` | `str` | OpenSubtitles API Key |
| `radarr_url/key` | `str` | Radarr 配置 |
| `sonarr_url/key` | `str` | Sonarr 配置 |
| `llm_provider` | `str` | `"cloud"` / `"local"` |
| `llm_cloud_url/key/model` | `str` | 云端 LLM 配置 |
| `llm_local_url/key/model` | `str` | 本地 LLM 配置 |
| `ai_name` | `str` | AI 助手名称 |
| `ai_persona` | `str` | AI 人格设定（System Prompt）|
| `expert_archive_rules` | `str` | 归档专家规则 |
| `master_router_rules` | `str` | 总控路由规则 |

### SettingsConfig

```python
class SettingsConfig(BaseModel):
    settings: SystemSettings
    paths: List[PathConfig] = []
```

`GET/POST /tasks/settings` 的请求/响应模型。

---

### 鉴权相关

```python
class LoginRequest(BaseModel):
    username: str
    password: str

class InitRequest(BaseModel):
    username: str = Field(..., min_length=3)
    password: str = Field(..., min_length=6)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str

class AuthStatusResponse(BaseModel):
    initialized: bool
    message: str
```

---

### 任务操作相关

```python
class DeleteBatchRequest(BaseModel):
    ids: List[int]

class PurgeRequest(BaseModel):
    confirm: str          # 必须传 "CONFIRM" 字符串

class ResetSettingsRequest(BaseModel):
    target: str           # "ai" | "regex"
```

---

### AI 对话相关

```python
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    action: Optional[str] = None
```
