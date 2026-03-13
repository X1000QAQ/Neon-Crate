# database — SQLite 数据库管理器

**文件路径**: `backend/app/infra/database/db_manager.py`  
**核心类**: `DatabaseManager`  
**单例访问**: `from app.infra.database import get_db_manager`  
**代码规模**: 1144 行

---

## 架构特性

| 特性 | 实现 |
|------|------|
| WAL 模式 | `PRAGMA journal_mode=WAL` — 读写并发不互斥 |
| 原子写入 | 所有写操作通过 `db_lock` (threading.Lock) 串行化 |
| 配置加密 | TMDB/OpenSubtitles/LLM API Key 通过 `CryptoManager` Fernet 加密存储 |
| 连接池 | 线程本地连接 (`threading.local`) |
| 孤儿任务清理 | 启动时自动重置上次崩溃遗留的 pending 任务 |

---

## 数据库表结构

### `tasks` 表 — 待处理任务队列

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PK | 自增主键 |
| `path` | TEXT UNIQUE | 原始文件物理路径 |
| `file_name` | TEXT | 文件名 |
| `type` | TEXT | `movie` / `tv` |
| `status` | TEXT | `pending` / `scraped` / `failed` / `archived` / `ignored` |
| `clean_name` | TEXT | 正则清洗后的片名 |
| `tmdb_id` | INTEGER | TMDB ID |
| `imdb_id` | TEXT | IMDb ID |
| `title` | TEXT | 匹配到的标题 |
| `year` | INTEGER | 发行年份 |
| `season` | INTEGER | 季号（剧集）|
| `episode` | INTEGER | 集号（剧集）|
| `poster_path` | TEXT | TMDB 海报路径 |
| `local_poster_path` | TEXT | 本地海报物理路径 |
| `target_path` | TEXT | 归档后目标路径 |
| `sub_status` | TEXT | 字幕状态 |
| `created_at` | DATETIME | 创建时间 |

### `media_archive` 表 — 已归档完成记录

存储状态为 `archived` 的完整记录，字段与 `tasks` 表基本一致，额外含：
- `archived_at`: 归档时间
- `link_type`: `hardlink` / `symlink`

### `config` 表 — 键值配置存储

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | TEXT PK | 配置键 |
| `value` | TEXT | 配置值（部分字段加密）|

---

## 核心方法速查

### 任务管理

```python
db.insert_task(task_data: dict) -> int
db.get_all_data(search_keyword=None) -> List[dict]
db.get_tasks_needing_scrape() -> List[dict]        # status=pending
db.get_tasks_needing_subtitles() -> List[dict]     # status=archived & sub_status!=scraped
db.check_task_exists_by_path(file_path: str) -> bool
db.update_task_status(task_id, status, tmdb_id=None, ...) -> None
db.update_task_title_year(task_id, title, year, season=None) -> None
db.delete_task(task_id: int) -> bool
db.delete_tasks_by_ids(ids: List[int]) -> None
db.clear_all_tasks() -> int                        # 核弹按钮，返回删除数量
db.reset_orphan_pending_tasks() -> int             # 启动时孤儿清理
```

### 归档查询

```python
db.get_archived_data(search_keyword=None) -> List[dict]
db.get_archive_stats() -> dict                     # {total: int}
db.update_archive_sub_status(archive_id, sub_status, last_check) -> None
```

### 配置管理

```python
db.get_config(key: str, default=None) -> Any
db.set_config(key: str, value: Any) -> None
db.get_all_config() -> dict                        # {settings: {}, paths: []}
db.save_all_config(config_dict: dict) -> None
db.get_agent_config(key: str, default="") -> str   # AI 人格配置专用
db.reset_settings_to_defaults(target: str) -> None # target='ai'|'regex'
```

### 路径与统计

```python
db.get_active_library_path(media_type: str) -> str  # 获取已启用的媒体库路径
db.get_dashboard_stats() -> dict                    # {pending, completed}
```

---

## 依赖注入方式

```python
# 路由端点（推荐）：通过 FastAPI Depends 注入
from app.api.v1.deps import DbDep

async def my_endpoint(db: DbDep):
    db.get_config("tmdb_api_key")

# 后台任务函数（唯一合理方式）：全局单例
from app.infra.database import get_db_manager

def my_background_task():
    db = get_db_manager()
    db.update_task_status(...)
```

> **说明**：`Depends()` 仅对 FastAPI 路由函数有效，`BackgroundTasks` 回调中必须使用 `get_db_manager()` 全局单例，这是 FastAPI 的设计规范，不是技术债。
