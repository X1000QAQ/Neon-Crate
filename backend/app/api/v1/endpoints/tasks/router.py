"""
router.py - tasks 路由包统一聚合器。

职责：
- 将扫描、刮削、重构、字幕、设置等任务子路由聚合为单一 `tasks.router`。
- 为 `app/api/v1/api.py` 提供 `/api/v1/tasks` 下的统一入口。
- 对媒体 CRUD 路由采用直接注册方式，精确保留 `GET /tasks` 的空路径契约。

路由聚合策略：
- 常规子路由使用 `include_router()`，保留各模块自身定义的路径。
- 媒体 CRUD 函数直接挂载到聚合 router，避免 FastAPI 将空路径转换为 `/` 后产生路由冲突。

维护提示：
- 修改这里的注册方式会直接影响前端请求路径。
- `GET ""` 与 `GET "/"` 在 FastAPI 中不是完全等价，不能随意替换。
"""
from fastapi import APIRouter

from app.api.v1.endpoints.tasks.scan_task import router as scan_router
from app.api.v1.endpoints.tasks.scrape_task import router as scrape_router
from app.api.v1.endpoints.tasks.rebuild_task import router as rebuild_router
from app.api.v1.endpoints.tasks.subtitle_task import router as subtitle_router
from app.api.v1.endpoints.tasks.settings_router import router as settings_router
from app.api.v1.endpoints.tasks.media_router import (
    router as media_router,
    get_all_tasks,
    delete_tasks_batch,
    delete_task_by_id,
    purge_all_tasks,
    retry_task,
    ignore_path,
    ignore_path_batch,
    unignore_path,
    get_ignore_list,
)

router = APIRouter()

# 聚合任务/设置/字幕子路由
router.include_router(scan_router)
router.include_router(scrape_router)
router.include_router(rebuild_router)
router.include_router(subtitle_router)
router.include_router(settings_router)

# 媒体库 CRUD 路由：直接注册到聚合 router 避免 GET "" 变成 GET "/"
router.get("")(get_all_tasks)
router.post("/delete_batch")(delete_tasks_batch)
router.delete("/{task_id}")(delete_task_by_id)
router.post("/purge")(purge_all_tasks)
router.post("/{task_id}/retry")(retry_task)
router.post("/ignore")(ignore_path)
router.post("/ignore_batch")(ignore_path_batch)
router.post("/unignore")(unignore_path)
router.get("/ignore_list")(get_ignore_list)
