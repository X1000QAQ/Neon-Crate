"""API v1 路由聚合"""
from fastapi import APIRouter
from app.api.v1.endpoints import tasks, system, agent

api_router = APIRouter()

# 注册子路由
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(agent.router, prefix="/agent", tags=["AI Agent"])
