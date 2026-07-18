"""
API v1 路由聚合器。

职责：
- 创建统一的 `api_router`，集中挂载 v1 版本下的业务子路由。
- 供 `app_factory.py` 挂载到 `/api/v1` 前缀下，形成稳定的版本化 API 入口。
- 保持各领域路由的 tag 和 prefix 清晰，便于 OpenAPI 文档分组。

路由分组：
- `/api/v1/tasks`：媒体任务、扫描、刮削、字幕、设置和 CRUD。
- `/api/v1/system`：系统统计、日志读取和图片代理。
- `/api/v1/agent`：AI 对话、意图识别、下载确认和授权执行。

维护提示：
- 本文件只负责路由挂载，不承载业务逻辑。
- 修改 prefix 会直接影响前端 API 地址，必须作为破坏性变更处理。
"""
from fastapi import APIRouter
from app.api.v1.endpoints import tasks, system, agent

api_router = APIRouter()

# 注册子路由
api_router.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
api_router.include_router(agent.router, prefix="/agent", tags=["AI Agent"])
