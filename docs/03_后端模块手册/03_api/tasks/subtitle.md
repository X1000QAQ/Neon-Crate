# subtitle_task — 字幕补完任务

**文件路径**: `backend/app/api/v1/endpoints/tasks/subtitle_task.py`

---

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/tasks/find_subtitles` | 触发全量字幕补完（后台线程池执行）|
| `GET` | `/tasks/find_subtitles/status` | 获取字幕任务状态 |

---

## 执行流程 (`perform_find_subtitles_task_sync`)

```
1. 前置检查：os_api_key 不为空
2. db.get_tasks_needing_subtitles()（status=archived 且 sub_status != scraped）
3. 初始化 SubtitleEngine(api_key, user_agent)

4. 对每个任务：
   SubtitleEngine.download_subtitle_for_task(
       db, file_path, tmdb_id, media_type,
       imdb_id, target_path, archive_id
   )
   └── 单任务失败 → continue，不中断队列
   └── 每条任务后 time.sleep(1) 避免 API 限流

5. 更新 find_subtitles_status
```

---

## GET /tasks/find_subtitles/status 响应

```json
{
  "is_running": false,
  "last_run_time": 1741737600.0,
  "processed_count": 12,
  "error": null
}
```

---

## 注意事项

- 字幕落盘路径优先使用 `target_path`（媒体库），确保字幕写入媒体库而不是下载目录
- 若目标目录已存在同名字幕文件，直接跳过（幂等）
- `sub_status` 更新：`scraped` / `missing` / `failed`

→ 字幕引擎详情见 [04_services/subtitle.md](../04_services/subtitle.md)
