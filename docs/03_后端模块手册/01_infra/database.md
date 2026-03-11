# 数据库模块手册 - `app/infra/database/`

> 路径：`backend/app/infra/database/db_manager.py`

> **重构说明（2026-03-11）**：`_inject_ai_defaults()` 的 `filename_clean_regex` 注入逻辑已从依赖 `MediaCleaner` 提取 pattern 改为直接硬编码 15 条默认规则字符串；强制覆盖条件由 `"从 MediaCleaner 自动提取" not in current_regex` 改为 `not current_regex`（只在为空时注入）。

---

## 一、模块概述

SQLite 数据库管理器，核心特性：
1. **WAL 模式**：Write-Ahead Logging，提升并发读取性能
2. **原子写入**：配置文件采用 `.tmp` 临时文件替换机制，防止写入中断导致损坏
3. **线程级连接池**：`threading.local()` 实现线程安全连接复用
4. **敏感密钥加密**：6 个敏感键自动通过 `CryptoManager` 加密存储
5. **自动明文迁移**：首次启动检测并迁移历史明文密钥
6. **AI 规则注入**：首次启动自动注入 AI 人格、路由规则、归档规则、正则清洗规则默认值

---

## 二、数据库表结构

### `tasks` 表（媒体任务主表）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | INTEGER PK | 自增主键 |
| `path` | TEXT UNIQUE | 原始文件路径（去重键）|
| `file_name` | TEXT | 文件名 |
| `clean_name` | TEXT | 清洗后名称 |
| `type` | TEXT | `movie` / `tv` |
| `status` | TEXT | `pending` / `scraped` / `archived` / `failed` / `ignored` |
| `tmdb_id` | TEXT | TMDB ID |
| `imdb_id` | TEXT | IMDB ID |
| `title` | TEXT | 作品标题 |
| `year` | TEXT | 年份 |
| `season` | INTEGER | 季号（剧集专用）|
| `episode` | INTEGER | 集号（剧集专用）|
| `poster_path` | TEXT | TMDB 海报路径 |
| `local_poster_path` | TEXT | 本地缓存海报路径 |
| `target_path` | TEXT | 归档后目标路径 |
| `sub_status` | TEXT | `pending` / `scraped` / `missing` / `failed` |
| `last_sub_check` | TEXT | 上次字幕检查时间 |
| `created_at` | TEXT | 创建时间 |

### `media_archive` 表（归档记录表）

归档完成后写入，记录完整归档信息，包含 `season`、`episode`、`sub_status` 等字段。

> **注意**：`media_archive.id` 与 `tasks.id` 是**各自独立自增**的，同一文件在两张表的 id 不同，删除时必须按 `path` 匹配，不能直接用 id 对删。

---

## 三、敏感键列表

以下 6 个配置键自动加密存储，读取时自动解密：

```python
SENSITIVE_KEYS = [
    "tmdb_api_key",
    "os_api_key",
    "sonarr_api_key",
    "radarr_api_key",
    "llm_cloud_key",
    "llm_local_key",
]
```

---

## 四、核心方法

### 配置读写

| 方法 | 说明 |
|---|---|
| `get_config(key, default)` | 读取配置，敏感键自动解密 |
| `set_config(key, value)` | 写入配置，敏感键自动加密 |
| `get_all_config()` | 获取完整配置（含 paths）|
| `get_agent_config(key, default)` | 读取 AI Agent 专用配置（同 get_config）|
| `save_all_config(config)` | 保存完整配置字典到 config.json（拦截并加密敏感键）|

### 任务管理

| 方法 | 说明 |
|---|---|
| `insert_task(path, file_name, ...)` | 插入新任务（path 唯一，重复忽略）|
| `get_all_data()` | 获取所有任务 |
| `update_task_status(task_id, status, ...)` | 更新任务状态 |
| `update_task_title_year(task_id, title, year, season)` | 更新作品标题、年份和季号（`season` 可选，剧集归档时传入路径补充后的修正值，确保数据库与归档路径保持一致）|
| `get_task_id_by_path(path)` | 按路径查找任务 ID |
| `check_imdb_id_exists(imdb_id)` | IMDB 查重（防止重复归档）|
| `get_dashboard_stats()` | 获取 Dashboard 统计数据 |
| `delete_task(task_id)` | 删除单条任务（同时按 `path` 清理 `media_archive` 残留，兜底按 `original_task_id` 删除）|
| `delete_tasks_by_ids(ids)` | 批量删除（先查 path 再双重清理 `media_archive`，防止 id 不一致导致残留）|

### 路径管理

| 方法 | 说明 |
|---|---|
| `get_managed_paths()` | 获取所有管理路径 |
| `get_all_config()` | 含 paths 数组的完整配置 |

### 配置重置

| 方法 | 说明 |
|---|---|
| `reset_settings_to_defaults(target)` | 重置为默认值。`target="ai"` 重置 AI 人格四项；`target="regex"` 重置 15 条正则规则 |

### 字幕状态

| 方法 | 说明 |
|---|---|
| `update_archive_sub_status(archive_id, sub_status, last_check)` | 更新归档记录字幕状态 |

---

## 五、AI 规则注入（`_inject_ai_defaults`）

服务首次启动时自动执行，对空字段注入工业默认值：

| 配置键 | 说明 |
|---|---|
| `ai_name` | AI 助手名称 |
| `ai_persona` | AI 人格 System Prompt |
| `expert_archive_rules` | 归档专家规则（JSON 输出约束）|
| `master_router_rules` | 总控路由规则（意图识别 JSON 指令）|
| `filename_clean_regex` | 15 条正则清洗规则（全局唯一真相源，`MediaCleaner` 和刮削任务均从此读取）|

**注入策略：只在字段为空时注入，不覆盖用户已有内容。**

---

## 六、全局单例

```python
from app.infra.database import get_db_manager

db = get_db_manager()  # 懒初始化单例
value = db.get_config("tmdb_api_key")  # 自动解密返回明文
```

---

## 七、注意事项

- 数据库文件路径由 `Settings.DB_PATH` 决定，默认 `data/media_database.db`
- 配置文件写入使用原子替换（写 `.tmp` → 重命名），防止断电损坏
- 线程级连接通过 `threading.local()` 隔离，避免 SQLite 跨线程冲突
- 首次启动自动执行 `_migrate_plaintext_keys()`，将历史明文密钥迁移为加密存储
- `get_db_manager()` 是懒初始化全局单例，整个进程共享同一个 `DatabaseManager` 实例
- `filename_clean_regex` 重置时注入 15 条规则（8条过滤 + 年份 + 6条季集），用户可自由增删
- `filename_clean_regex` 是**系统唯一正则真相源**，`MediaCleaner` 和刮削任务均从此读取，严禁在代码里硬编码任何过滤正则

---

## 八、双表删除机制

`tasks` 与 `media_archive` 是**各自独立自增 ID** 的两张表，同一个文件在两张表中的 `id` 不相同。

旧版 `delete_task(task_id)` 错误地用 `tasks.id` 去删 `media_archive.id`，导致归档记录残留，重新扫描时被 `check_task_exists_by_path()` 命中而跳过入库（文件永远无法重新刮削）。

**修复后删除逻辑：**

```
delete_task(task_id):
  1. 先查 tasks 中该 id 对应的 path
  2. DELETE FROM tasks WHERE id = ?
  3. DELETE FROM media_archive WHERE path = ?              ← 按路径（最准确）
  4. DELETE FROM media_archive WHERE original_task_id = ?  ← 兜底
```

`delete_tasks_by_ids(ids)` 同理，先批量查 path，再按 path 和 original_task_id 双重清理 `media_archive`。

---

*最后更新：2026-03-11*
