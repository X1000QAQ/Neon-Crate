# media_router — 媒体库 CRUD 路由

**文件路径**: `backend/app/api/v1/endpoints/tasks/media_router.py`  
**依赖注入**: `db: DbDep`

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/tasks` | 获取任务列表 |
| `POST` | `/tasks/delete_batch` | 批量删除 |
| `DELETE` | `/tasks/{task_id}` | 单条删除 |
| `POST` | `/tasks/purge` | 清空全部（核弹）|
| `POST` | `/tasks/{task_id}/retry` | 重置为 pending |

---

## GET /tasks 查询参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `search` | string | 关键词搜索 |
| `status` | string | `pending`/`scraped`/`failed`/`archived`/`all` |
| `media_type` | string | `movie`/`tv`/`all` |
| `page` | int | 页码 |
| `page_size` | int | 每页条数 |

### 数据来源

| status 参数 | 查询表 |
|-------------|--------|
| `"archived"` | `media_archive` 表 |
| `null` / `"all"` | `tasks` + `media_archive` 合并 |
| 其他状态 | `tasks` 表 |

### 响应体

```json
{
  "tasks": [{...}],
  "total": 100,
  "page": 1,
  "page_size": 100
}
```

### 字段标准化处理

- `type` → `media_type`（数据库字段映射为前端字段）
- `path` / `target_path` / `poster_path` → 统一转为正斜杠（`Path.as_posix()`）
- 补充 `file_path` 别名字段（指向 `path`）

---

## POST /tasks/purge

```json
// 请求体（防误触设计）
{ "confirm": "CONFIRM" }
// 响应
{ "success": true, "deleted": 165, "message": "已清空 165 条任务记录" }
```

---

## POST /tasks/{task_id}/retry

将任务状态重置为 `pending`，等待下次刮削任务处理。  
支持 `tasks` 表和 `media_archive` 表中的记录。
