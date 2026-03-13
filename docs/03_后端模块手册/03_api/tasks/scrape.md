# scrape_task — 全量刮削任务

**文件路径**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`

---

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/tasks/scrape_all` | 触发全量刮削（后台线程池执行）|

---

## 执行流程 (`perform_scrape_all_task_sync`)

```
1. 前置检查：tmdb_api_key 不为空
2. 获取 db.get_tasks_needing_scrape()（status=pending）
3. 初始化 TMDBAdapter + AIAgent

4. 对每个任务：
   a. MediaCleaner.clean_name() 正则前置清洗
   b. AIAgent.ai_identify_media() AI 识别片名/年份/类型
   c. 路径权威：db type 优先，AI 建议次之
   d. TMDBAdapter.search_movie/tv() 搜索
      └── 匹配失败时对剧集尝试截取首词二次搜索
   e. 精确匹配逻辑（original_title 完全匹配优先）
   f. 获取 IMDB ID（get_external_ids）
   g. SmartLink 归档（硬链接/软链接）
   h. MetadataManager 下载 NFO + 海报 + Fanart
   i. db.update_task_status(status="archived", tmdb_id=int(tmdb_id))
   └── 单任务失败 → continue，不中断队列

5. _update_library_counts()
```

---

## 错误隔离层级

```
外层 for task in tasks_to_scrape:
  try/except → continue          # 任务级隔离
  │
  └── 归档流程内部：
      ├── NFO 生成    try/except  # 失败仅 warning
      ├── 海报下载    try/except  # 失败不影响 DB 写入
      └── Fanart      try/except  # 失败不影响 DB 写入
```

---

## 孤儿任务兜底

```python
# 外层 except（整个任务函数崩溃时）
orphan_tasks = db.get_tasks_needing_scrape()
for orphan in orphan_tasks:
    db.update_task_status(orphan["id"], "failed")
```

服务重启时由 `lifespan.py` 调用 `db.reset_orphan_pending_tasks()` 二次兜底。

---

## 关键修复记录

| 修复点 | 说明 |
|--------|------|
| `tmdb_id=int(tmdb_id)` | 原 `str(tmdb_id)` 与 `Task.tmdb_id: Optional[int]` 契约不符，已修复 |
| AI 返回值验证 | `isinstance(ai_result, dict)` 防 None 崩溃 |
| 路径穿越拦截 | `Path.resolve().relative_to(library_root)` |
