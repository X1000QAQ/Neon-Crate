# scan_task — 物理扫描任务

**文件路径**: `backend/app/api/v1/endpoints/tasks/scan_task.py`

---

## 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/tasks/scan` | 触发扫描，立即返回，任务后台执行 |
| `GET` | `/tasks/scan/status` | 查询当前扫描状态 |

---

## 执行流程 (`perform_scan_task`)

```
1. 读取数据库配置
   └── 筛选 type="download" && enabled=True 的路径
   └── 读取 min_size_mb（优先级: min_size_mb > min_file_size_mb > 50）

2. 实例化 ScanEngine(max_workers=4, min_size_mb, db_manager)

3. 遍历 download 路径执行 scan_directory(recursive=True)

4. 智能入库
   ├── check_task_exists_by_path() → 已存在跳过
   ├── 路径霸权机制（见下方）
   └── db.insert_task()

5. 更新 scan_status + _update_library_counts()
```

---

## 路径霸权机制

| 路径配置 category | task_type 来源 |
|-------------------|---------------|
| `"movie"` | 强制 `movie` |
| `"tv"` | 强制 `tv` |
| `"mixed"` / `"download"` / 其他 | 使用 MediaCleaner 正则猜测 |

强制认定为 `movie` 时，自动清空 `season` / `episode` 字段。

---

## GET /tasks/scan/status 响应

```json
{
  "is_running": false,
  "last_scan_time": 1741737600.0,
  "last_scan_count": 5,
  "error": null
}
```

---

## 防重叠

```python
if scan_status["is_running"]:
    return ScanResponse(message="扫描任务已在运行中，请稍后再试")
```
