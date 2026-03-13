"""
router.py - tasks 包统一路由聚合器

设计目标：
- 将所有子模块的 router 合并为单一的 tasks_router
- 供 app/api/v1/api.py 通过 tasks.router 挂载

路由聚合策略：
- 常规子路由：直接 include_router（自动携带前缀）
- 媒体 CRUD 路由：直接注册函数（避免 GET "" 变成 GET "/"）

特殊说明（媒体 CRUD 路由直接注册）：
- get_all_tasks：GET "" 而非 GET "/"，FastAPI 对空路径有特殊处理
- 如果用 include_router，GET "" 会变成 GET "/"，导致路由冲突
- 解决方案：直接注册路由函数，精确控制路径
"""
from fastapi import APIRouter

from app.api.v1.endpoints.tasks.scan_task import router as scan_router
from app.api.v1.endpoints.tasks.scrape_task import router as scrape_router
from app.api.v1.endpoints.tasks.subtitle_task import router as subtitle_router
from app.api.v1.endpoints.tasks.settings_router import router as settings_router
from app.api.v1.endpoints.tasks.media_router import (
    router as media_router,
    get_all_tasks,
    delete_tasks_batch,
    delete_task_by_id,
    purge_all_tasks,
    retry_task,
)

router = APIRouter()

# 聚合任务/设置/字幕子路由
router.include_router(scan_router)
router.include_router(scrape_router)
router.include_router(subtitle_router)
router.include_router(settings_router)

# 媒体库 CRUD 路由：直接注册到聚合 router 避免 GET "" 变成 GET "/"
router.get("")(get_all_tasks)
router.post("/delete_batch")(delete_tasks_batch)
router.delete("/{task_id}")(delete_task_by_id)
router.post("/purge")(purge_all_tasks)
router.post("/{task_id}/retry")(retry_task)
