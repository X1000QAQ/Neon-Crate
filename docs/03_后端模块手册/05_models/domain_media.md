# domain_media — 媒体领域模型

**文件路径**: `backend/app/models/domain_media.py`

---

## 模型列表

### Task

媒体任务的核心 Pydantic 模型，用于 API 响应序列化。

```python
class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    file_path: str
    file_name: Optional[str] = None
    media_type: str          # "movie" | "tv"（无 alias，字段名即 media_type）
    status: str              # pending | scraped | failed | archived | ignored
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    poster_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    target_path: Optional[str] = None
    sub_status: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    created_at: Optional[str] = None
```

**重要**：`media_type` 字段无 `alias`，数据库字段 `type` 在 `media_router.py` 中手动映射为 `media_type` 后返回。

---

### StatsResponse

```python
class StatsResponse(BaseModel):
    movies: int = 0
    tv_shows: int = 0
    pending: int = 0
    completed: int = 0
```

---

### ScanResponse

```python
class ScanResponse(BaseModel):
    message: str
    task_id: Optional[str] = None
```

用于扫描/刮削/字幕任务的触发响应。

---

## 前后端类型对齐

| 字段 | 后端类型 | 前端类型 | 状态 |
|------|---------|---------|------|
| `media_type` | `str` | `'movie' \| 'tv'` | ✅ |
| `tmdb_id` | `Optional[int]` | `number?` | ✅ |
| `year` | `Optional[int]` | `number?` | ✅ |
| `status` | `str` | `'pending'\|'scraped'\|'failed'\|'archived'\|'ignored'` | ✅ |
