"""
Neon Crate Server - FastAPI 后端应用入口

架构设计：
- 应用工厂模式：app_factory.py 负责应用创建和配置
- 生命周期管理：lifespan.py 负责启动/关闭逻辑
- CLI 支持：cli.py 提供命令行工具
- 本文件：仅作为应用入口，保持极简

启动方式：
1. Web 服务：python -m app.main
2. CLI 工具：python -m app.cli reset-password
3. Docker：uvicorn app.main:app --host 0.0.0.0 --port 8000

设计理念：
- 单一职责：main.py 只负责启动，不包含业务逻辑
- 解耦合：应用创建和配置分离到 app_factory.py
- 可测试：通过工厂模式方便单元测试
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
