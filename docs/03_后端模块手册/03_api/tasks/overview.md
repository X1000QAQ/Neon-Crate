# tasks 包总览

**目录**: `backend/app/api/v1/endpoints/tasks/`  
**路由前缀**: `/api/v1/tasks`

---

## 包结构

```
tasks/
├── __init__.py          # 重导出，供 lifespan.py 的 cron_scanner_loop 使用
├── _shared.py           # 全局任务状态字典 + _update_library_counts()
├── router.py            # 路由聚合器（统一出口）
├── scan_task.py         # 物理扫描任务
├── scrape_task.py       # 全量刮削任务
├── subtitle_task.py     # 字幕补完任务
├── media_router.py      # 媒体库 CRUD 路由
└── settings_router.py   # 系统配置路由
```

---

## 路由全表

| 方法 | 路径 | 子模块 | 说明 |
|------|------|--------|------|
| `POST` | `/tasks/scan` | scan_task | 触发物理扫描 |
| `GET` | `/tasks/scan/status` | scan_task | 获取扫描状态 |
| `POST` | `/tasks/scrape_all` | scrape_task | 触发全量刮削 |
| `POST` | `/tasks/find_subtitles` | subtitle_task | 触发字幕补完 |
| `GET` | `/tasks/find_subtitles/status` | subtitle_task | 获取字幕任务状态 |
| `GET` | `/tasks` | media_router | 获取任务列表（支持过滤/分页）|
| `POST` | `/tasks/delete_batch` | media_router | 批量删除任务 |
| `DELETE` | `/tasks/{task_id}` | media_router | 删除单条任务 |
| `POST` | `/tasks/purge` | media_router | 清空全部任务（核弹）|
| `POST` | `/tasks/{task_id}/retry` | media_router | 重置任务为 pending |
| `GET` | `/tasks/settings` | settings_router | 获取系统配置 |
| `POST` | `/tasks/settings` | settings_router | 更新系统配置 |
| `POST` | `/tasks/settings/reset` | settings_router | 重置 AI/Regex 配置 |

---

## _shared.py — 共享状态

```python
# 全局任务状态字典（内存）
scan_status = {
    "is_running": False,
    "last_scan_time": None,
    "last_scan_count": 0,
    "error": None
}

scrape_all_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}

find_subtitles_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}
```

`_update_library_counts()` 在扫描/刮削完成后调用，物理统计媒体库文件数量并写入数据库缓存。

---

## router.py — 路由聚合器

```python
router = APIRouter()

router.include_router(scan_router)
router.include_router(scrape_router)
router.include_router(subtitle_router)
router.include_router(settings_router)

# media_router 路由直接注册（避免 GET "" 变成 GET "/"）
router.get("")(get_all_tasks)
router.post("/delete_batch")(delete_tasks_batch)
router.delete("/{task_id}")(delete_task_by_id)
router.post("/purge")(purge_all_tasks)
router.post("/{task_id}/retry")(retry_task)
```

→ 子模块详见：[scan.md](scan.md) | [scrape.md](scrape.md) | [subtitle.md](subtitle.md) | [media.md](media.md) | [settings.md](settings.md)
