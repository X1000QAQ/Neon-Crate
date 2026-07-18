"""
应用工厂 - FastAPI 应用创建与装配中心

职责：
- 创建 FastAPI 应用实例。
- 按固定顺序注册 CORS 中间件、鉴权路由、业务路由、异常处理器、健康检查和静态资源。
- 提供 `/docs` 与 `/redoc` 文档入口，并在 AIO 模式下托管前端 SPA 静态文件。

装配顺序：
1. `_register_middleware()`：先注册 CORS，确保跨域策略覆盖后续路由。
2. `_register_routers()`：注册鉴权、公有图片代理和受保护业务 API。
3. `_register_exception_handlers()`：注册全局异常处理和 SPA 404 回退。
4. `_add_health_check()`：添加容器健康检查端点。
5. 文档路由：注册 `/docs`、`/redoc`，避免被根路径静态资源吞掉。
6. `_mount_static_resources()`：最后挂载 `/api/v1/assets`、`/static/docs` 和 `/` 前端资源。

维护提示：
- 根路径 `StaticFiles` 必须最后挂载，否则 `/docs`、`/redoc` 和部分 API 路由可能被 SPA 捕获。
- 鉴权路由必须独立注册，不能被全局 JWT 依赖保护。
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
    注册应用级中间件。

    当前只注册 CORS：
    - AIO 同域部署下通常不会触发跨域。
    - 局域网直连 API 或前后端分离调试时依赖该策略放行。
    - 认证凭据使用 Authorization 头，不依赖 Cookie。
    """
    # CORS 策略（现状）：
    # 1. AIO 同域场景下常规导航不触发预检。
    # 2. 局域网 Origin 直连 API 时须与 CORS_ORIGINS 对齐，否则浏览器拦截跨域响应。
    # 3. 凭据走 Authorization 头而非 Cookie，故 allow_credentials=False 与通配源策略可共存。
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
    """
    注册全局异常处理器。

    处理范围：
    - 未捕获异常统一转为 500 JSON，生产环境隐藏内部异常细节。
    - 非 `/api` 的 404 优先回退到 SPA `index.html`，支持前端路由刷新。
    - `/api` 前缀 404 保持 JSON，不让 API 错误落入前端页面。
    """
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

        路径契约：
        - index.html 以相对 app_factory 的绝对路径解析，与容器工作目录解耦
        - /api 前缀 404 返回 JSON，不注入 SPA，避免 API 误落入前端路由
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
        # html=False: 支持目录结构的 Next.js 导出模式
        # 当请求 /auth/login/ 时，自动返回 /auth/login/index.html
        app.mount("/", StaticFiles(directory=frontend_static, html=False), name="frontend")
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
    创建并装配 FastAPI 应用。

    装配顺序是运行时契约：
    1. 注册中间件。
    2. 注册鉴权路由、公有路由和受保护业务路由。
    3. 注册异常处理器和健康检查。
    4. 注册自定义文档路由。
    5. 最后挂载静态资源和 SPA 根路径。

    Args:
        lifespan: 可选生命周期管理器，通常来自 `app.core.lifespan.lifespan`。

    Returns:
        FastAPI: 配置完成的应用实例。
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
    
    # 挂载次序：先于根路径 StaticFiles 注册 /docs、/redoc 等文档路由，避免被 / 通配吞掉
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
    
    # 挂载次序：文档与业务路由全部就绪后，再挂载「/」SPA 静态，保证 /docs、/redoc 优先匹配
    _mount_static_resources(app)

    return app
