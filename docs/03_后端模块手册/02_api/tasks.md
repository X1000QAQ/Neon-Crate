# 任务端点手册 - `app/api/v1/endpoints/tasks.py`

> 路径：`backend/app/api/v1/endpoints/tasks.py`
> 路由前缀：`/api/v1/tasks`

> **重构说明（2026-03-11）**：`ScanEngine` 实例化时新增传入 `db_manager=db`，使 `MediaCleaner` 能从数据库加载正则规则。刮削流程新增以下修复：
> 1. **正则军火库统一**：刮削前置清洗完全委托给 `MediaCleaner(db_manager=db).clean_name()`，不再有任何硬编码过滤正则
> 2. **TMDB 精确匹配**：搜索结果优先按 `original_title`/`original_name` 与 query 完全匹配，宽松匹配去末尾集号后再比对，解决同名歧义（如「The Boys」命中「哈迪兄弟」）
> 3. **季号回写**：归档时将路径补充后的 `season_num` 通过 `update_task_title_year(season=season_num)` 写回数据库，确保前端显示与归档路径一致
> 4. **路径季号补充**：归档构建路径时，若数据库 `season=1` 则从原始路径 `Season XX` 目录名补充真实季号

---

## 一、模块概述

系统核心任务端点，覆盖：扫描、刮削、字幕、归档、设置读写、媒体库查询、任务管理等所有业务操作。

---

## 二、接口列表

### 扫描类

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/tasks/scan` | 触发物理扫描（BackgroundTasks 异步）|
| `GET` | `/tasks/scan/status` | 查询扫描任务运行状态 |

### 刮削类

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/tasks/scrape_all` | 触发全量刮削（后台线程）|
| `GET` | `/tasks/scrape_all/status` | 查询刮削任务状态 |

### 字幕类

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/tasks/find_subtitles` | 触发全量字幕查找 |
| `GET` | `/tasks/find_subtitles/status` | 查询字幕任务状态 |

### 设置类

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/tasks/settings` | 读取完整系统配置（`SettingsConfig`）|
| `POST` | `/tasks/settings` | 更新系统配置（含 1+1 路径约束校验）|
| `POST` | `/tasks/settings/reset` | 重置配置为默认值（`target=ai` 或 `target=regex`）|

### 媒体库查询

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/tasks/` | 任务列表（分页 + 搜索 + 状态/类型过滤）|
| `GET` | `/tasks/{task_id}` | 单条任务详情 |
| `DELETE` | `/tasks/{task_id}` | 删除单条任务（同时清理 `media_archive` 残留）|
| `POST` | `/tasks/delete_batch` | 批量删除（`DeleteBatchRequest`）|
| `POST` | `/tasks/purge` | 清空所有任务（`PurgeRequest`，同时清空两张表）|

### 任务操作

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/tasks/{task_id}/retry` | 重试失败任务（重新刮削）|
| `POST` | `/tasks/{task_id}/ignore` | 标记任务为 ignored |
| `POST` | `/tasks/{task_id}/archive` | 手动触发单条归档 |

---

## 三、任务状态机

```
pending
  ├─► scraped    (刮削成功)
  │     └─► archived  (归档成功)
  ├─► failed     (刮削/归档失败)
  │     └─► pending   (retry 重置)
  └─► ignored    (手动跳过)
```

---

## 四、全局任务状态跟踪

三个模块级字典用于防止重复触发：

```python
scan_status = {"is_running": False, "last_scan_time": None, ...}
scrape_all_status = {"is_running": False, "last_run_time": None, ...}
find_subtitles_status = {"is_running": False, "last_run_time": None, ...}
```

任务运行中再次触发会直接返回 `"任务已在运行中"` 而不重复执行。

---

## 五、刮削流程（`perform_scrape_all_task_sync`）

### 5.1 正则军火库：物理级前置拦截器

```python
# 完全委托给 MediaCleaner，无任何硬编码过滤正则
raw_filename = file_name or file_path.split('/')[-1]
cleaned_filename = MediaCleaner(db_manager=db).clean_name(raw_filename)
# 兜底：清洗结果为空时回退原始名
if not cleaned_filename:
    cleaned_filename = raw_filename
```

`MediaCleaner.clean_name()` 清洗步骤：
1. 去扩展名
2. 去首部方括号组名（`[HbT]`、`[DBD-Raws]` 等 20 字以内）
3. 去所有剩余方括号内容
4. 执行数据库 `filename_clean_regex`（全部 15 条规则）
5. 符号清理 + 多余空格折叠

### 5.2 TMDB 精确匹配

```
results = scraper.search_tv(query, year)
  ├─ 优先：original_name == query（严格）
  ├─ 其次：name == query（严格）
  ├─ 宽松：去末尾集号后再匹配（"The Boys 02" → "The Boys"）
  └─ 兜底：results[0]
```

### 5.3 季号补充与回写

```
归档构建路径时：
  season_num = task.get("season") or 1
  if season_num == 1:
      从 Path(file_path).parts 中搜索 Season XX 目录名
      若找到非1的季号 → 覆盖 season_num

写入数据库：
  update_task_title_year(task_id, title, year, season=season_num)
  → tasks.season 更新为修正值
  → archive_task() 将修正后的 season 复制到 media_archive
  → 前端显示 season 与归档路径一致
```

---

## 六、扫描流程关键改动（2026-03-11）

```python
# 旧代码
scan_engine = ScanEngine(max_workers=4, min_size_mb=min_size_mb)

# 新代码（传入 db_manager，使 MediaCleaner 能读取数据库正则）
scan_engine = ScanEngine(max_workers=4, min_size_mb=min_size_mb, db_manager=db)
```

---

## 七、注意事项

- 所有接口受全局 JWT 保护（`main.py` 挂载）
- 刮削和字幕任务使用 `threading.Thread` 在独立线程执行，避免阻塞 asyncio 事件循环
- `purge` 操作不可撤销，会物理删除 `tasks` 和 `media_archive` 两张表的记录
- 设置保存前执行 1+1 路径约束：同时只能启用 1 个电影库 + 1 个剧集库
- 正则清洗**严禁**在 tasks.py 内硬编码，所有过滤规则必须来自数据库 `filename_clean_regex`

---

*最后更新：2026-03-11*
