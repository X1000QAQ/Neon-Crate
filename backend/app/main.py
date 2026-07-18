"""
Neon Crate Server - FastAPI 后端 ASGI 入口

职责：
- 从 `app.core.app_factory.create_app()` 创建 FastAPI 应用实例。
- 将 `app.core.lifespan.lifespan` 注入应用工厂，绑定启动和关闭生命周期。
- 在直接执行 `python -m app.main` 时，根据命令行参数选择 Web 服务或 CLI 模式。

边界：
- 本文件不注册路由、不初始化数据库、不实现业务逻辑。
- 应用装配细节集中在 `app_factory.py`，启动/关闭资源管理集中在 `lifespan.py`。
- Docker / Uvicorn 部署时通过 `app.main:app` 暴露 ASGI 应用。

启动方式：
1. Web 服务：`python -m app.main`
2. CLI 工具：`python -m app.cli reset-password`
3. Docker / Uvicorn：`uvicorn app.main:app --host 0.0.0.0 --port 8000`
"""
import sys

from app.core.app_factory import create_app
from app.core.lifespan import lifespan
from app.infra.config import settings

# 创建应用实例
app = create_app(lifespan=lifespan)


if __name__ == "__main__":
    # 检查是否是 CLI 模式
    if len(sys.argv) > 1 and sys.argv[1] in ['reset-password', 'show-admin', 'init-admin', '--help', '-h']:
        from app.cli import cli
        cli()
    else:
        # 正常启动 Web 服务
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=False,
            workers=1,
            log_level=settings.LOG_LEVEL.lower(),
            access_log=True
        )
