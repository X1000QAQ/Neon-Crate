"""
应用工厂 - FastAPI 应用创建与配置

设计模式：工厂模式
- 解耦 main.py 的单点故障
- 提供统一的应用创建接口
- 便于单元测试和集成测试

核心职责:
1. 创建 FastAPI 应用实例
2. 注册所有中间件（CORS、认证等）
3. 注册所有路由（API、静态资源等）
4. 配置异常处理器（全局异常捕获、SPA 回退）
5. 挂载静态资源（海报、前端文件等）

配置顺序：
- 中间件 → 路由 → 异常处理器 → 健康检查 → 静态资源
- 顺序很重要，不可随意调整

SPA 支持：
- 404 自动回退到 index.html
- API 路由优先级高于静态文件
"""
import os
import logging
from pathlib import Path
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse

from app.infra.config import settings
from app.api.auth import get_current_user


def _register_middleware(app: FastAPI) -> None:
    """
    注册所有中间件
    
    当前中间件：
    - CORSMiddleware：跨域资源共享
      - allow_origins：允许的前端域名（从配置读取）
      - allow_credentials：允许携带 Cookie
      - allow_methods：允许所有 HTTP 方法
      - allow_headers：允许所有请求头
    """
    # CORS 修复说明：
    # 1. AIO 单容器部署下，前后端同域，正常页面请求不触发 CORS 预检。
    # 2. 局域网设备（如 192.168.x.x）直接请求 /api/v1/* 时，浏览器会附带 Origin 头，
    #    必须放行所有来源，否则出现 403/CORS error。
    # 3. allow_origins=["*"] 与 allow_credentials=True 不兼容（CORS 规范），
    #    JWT 通过 Authorization header 传递，无需 Cookie，故 allow_credentials=False 安全可行。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _register_routers(app: FastAPI) -> None:
    """
    注册所有路由
    
    路由注册顺序（重要，不可调换）：
    1. 鉴权路由（/api/v1/auth）：无需 JWT，公开访问
    2. 图片代理路由（/api/v1/public）：需要 JWT 鉴权
    3. 业务路由（/api/v1）：全局 JWT 保护，所有接口均需认证
    
    全局 JWT 保护机制：
    - 通过 dependencies=[Depends(get_current_user)] 注入
    - 无需在每个路由单独添加认证逻辑
    - 鉴权路由单独注册，不受全局保护影响
    """
    from app.api.auth import router as auth_router
    from app.api.v1.api import api_router
    from app.api.v1.endpoints.system import public_router as public_system_router

    # 鉴权路由必须在最前面
    app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])

    # 图片代理路由（需要 JWT 鉴权）
    app.include_router(
        public_system_router,
        prefix=f"{settings.API_V1_PREFIX}/public",
        tags=["Public System"],
        dependencies=[Depends(get_current_user)]
    )

    # 业务路由（全局 JWT 保护）
    app.include_router(
        api_router,
        prefix=settings.API_V1_PREFIX,
        dependencies=[Depends(get_current_user)]
    )


def _register_exception_handlers(app: FastAPI) -> None:
    """注册异常处理器"""
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        """全局异常捕获"""
        logging.error(f"[ERROR] 未处理的异常: {str(exc)}", exc_info=True)
        import os
        is_debug = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
        safe_message = f"服务器内部错误: {str(exc)}" if is_debug else "服务器内部错误，请联系管理员"
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": safe_message,
                "data": None
            }
        )

    @app.exception_handler(404)
    async def spa_fallback_handler(request, exc):
        """
        SPA 单页应用 404 回退

        修复要点：
        - 使用绝对路径定位 index.html，避免 Docker CWD 不确定导致找不到文件
        - API 路由 404 仍返回 JSON，不回退到前端
        """
        if request.url.path.startswith("/api"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

        # 使用绝对路径：app_factory.py -> core/ -> app/ -> backend/ -> static/
        index_path = Path(__file__).resolve().parent.parent.parent / "static" / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        else:
            return JSONResponse(status_code=404, content={"detail": "Not Found"})


def _mount_static_resources(app: FastAPI) -> None:
    """
    挂载静态资源
    
    挂载顺序（重要）：
    1. /api/v1/assets：媒体资源（海报、Fanart 等）
       - Docker 优先：DOCKER_STORAGE_PATH（/media 等挂载点）
       - 本地回退：data/posters 目录
    2. /static/docs：API 文档静态资源（Swagger UI）
       - 如果存在则挂载，支持离线环境
    3. /：前端静态文件（SPA）
       - 需要 static/index.html 存在才会挂载
       - 不存在时跳过（纯 API 模式）
    
    AIO 模式：
    - 前后端一体化部署
    - 前端编译产物放入 static/ 目录
    - uvicorn 同时提供 API 和前端服务
    """
    from fastapi.staticfiles import StaticFiles

    # 挂载资源目录
    assets_dir = None
    if os.path.isdir(settings.DOCKER_STORAGE_PATH):
        assets_dir = settings.DOCKER_STORAGE_PATH
        logging.info(f"[OK] 静态资源已挂载: {settings.DOCKER_STORAGE_PATH} -> /api/v1/assets")
    else:
        fallback_dir = Path(__file__).resolve().parent.parent.parent / "data" / "posters"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = str(fallback_dir)
        logging.info(f"[OK] 静态资源已挂载（回退）: {assets_dir} -> /api/v1/assets")

    if assets_dir:
        app.mount("/api/v1/assets", StaticFiles(directory=assets_dir), name="assets")

    # 挂载 API 文档静态资源（新增 - 支持离线环境）
    docs_static = Path(__file__).resolve().parent.parent.parent / "static" / "docs"
    if docs_static.exists() and docs_static.is_dir():
        app.mount("/static/docs", StaticFiles(directory=str(docs_static)), name="docs")
        logging.info(f"[OK] API 文档静态资源已挂载: {docs_static} -> /static/docs")

    # 挂载前端静态文件
    # 使用绝对路径，确保 Docker 容器内 CWD 不影响挂载
    frontend_static_abs = Path(__file__).resolve().parent.parent.parent / "static"
    frontend_static = str(frontend_static_abs)
    if frontend_static_abs.is_dir():
        app.mount("/", StaticFiles(directory=frontend_static, html=True), name="frontend")
        logging.info(f"[OK] 前端静态文件已挂载: {frontend_static} -> /")
    else:
        logging.info(f"[INFO] 未找到前端静态目录 {frontend_static}，AIO 模式未启用")


def _add_health_check(app: FastAPI) -> None:
    """添加健康检查端点"""
    @app.get("/health", tags=["System Status"])
    async def health_check():
        """健康检查端点（脱敏：不暴露版本号与时间戳）"""
        return {"status": "online"}


def create_app(lifespan=None) -> FastAPI:
    """
    创建并配置 FastAPI 应用

    Args:
        lifespan: 可选的生命周期管理器

    Returns:
        FastAPI: 配置完成的应用实例
    """
    app = FastAPI(
        title="Neon Crate API Gateway",
        description="Quantum Data Container Orchestration Engine // 神经链路核心 API 接口库",
        version="2.1.0",
        docs_url=None,  # 禁用默认 Swagger UI，改用自定义路由
        redoc_url=None,  # 原生 ReDoc 无法访问，由 Scalar 接管
        lifespan=lifespan,
        openapi_tags=[
            {
                "name": "Tasks",
                "description": "媒体任务核心接口：扫描、刮削、字幕搜索、CRUD 操作",
            },
            {
                "name": "System",
                "description": "系统监控：统计数据、日志流、图片代理、配置管理",
            },
            {
                "name": "AI Agent",
                "description": "AI 对话助手：意图识别、自然语言下载触发、流式聊天",
            },
            {
                "name": "System Status",
                "description": "服务健康探测：容器存活检查、就绪探针",
            },
        ],
    )

    # 按顺序配置应用
    _register_middleware(app)
    _register_routers(app)
    _register_exception_handlers(app)
    _add_health_check(app)
    
    # ⚠️ 关键修复：在挂载静态资源之前定义所有特定路由
    # 自定义 Swagger UI（支持本地资源回退）
    from fastapi.openapi.docs import get_swagger_ui_html
    
    @app.get("/docs", include_in_schema=False)
    async def custom_swagger_ui_html():
        """
        自定义 Swagger UI 文档路由
        
        离线支持：
        - 优先使用本地资源（/static/docs/）
        - 本地资源不存在时回退到 CDN
        - 通过 download_docs_assets.py 脚本可下载本地资源
        """
        # 修正路径：确保指向 backend/static/docs
        docs_static = Path(__file__).resolve().parent.parent.parent / "static" / "docs"
        
        # 检查本地资源是否存在
        local_bundle = docs_static / "swagger-ui-bundle.js"
        local_css = docs_static / "swagger-ui.css"
        
        if local_bundle.exists() and local_css.exists():
            # 使用本地资源（离线模式）
            logging.info(f"[DOCS] 使用本地 Swagger UI 资源: {docs_static}")
            return get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - API Documentation",
                swagger_js_url="/static/docs/swagger-ui-bundle.js",
                swagger_css_url="/static/docs/swagger-ui.css",
            )
        else:
            # 回退到 CDN（在线模式）
            logging.warning(f"[DOCS] 本地资源不存在，回退到 CDN: {docs_static}")
            return get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{app.title} - API Documentation",
            )

    # Scalar API 文档引擎（替代原生 ReDoc）
    @app.get("/redoc", include_in_schema=False)
    async def scalar_html():
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{app.title} - API Reference</title>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
</head>
<body>
    <script id="api-reference" data-url="{app.openapi_url}"></script>
    <script src="https://cdn.jsdelivr.net/npm/@scalar/api-reference"></script>
</body>
</html>"""
        return HTMLResponse(html_content)
    
    # ⚠️ 关键修复：静态资源挂载必须在所有路由定义之后
    # 这样 / 根路径才不会覆盖 /docs 和 /redoc
    _mount_static_resources(app)

    return app
