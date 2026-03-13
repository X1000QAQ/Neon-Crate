"""API v1 路由聚合器

职责：
- 将所有子模块的路由聚合到统一的 api_router
- 供 app_factory.py 挂载到 /api/v1 前缀下

路由前缀：
- /api/v1/tasks  — 媒体任务（扫描、刮削、字幕、设置、CRUD）
- /api/v1/system — 系统监控（统计、日志、图片代理）
- /api/v1/agent  — AI 对话（聊天、意图识别、下载触发）
"""
from fastapi import APIRouter
from app.api.v1.endpoints import tasks, system, agent

api_router = APIRouter()

# 注册子路由
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(agent.router, prefix="/agent", tags=["AI Agent"])
