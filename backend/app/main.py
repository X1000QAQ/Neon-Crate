"""
Neon Crate Server - FastAPI 后端应用
数字容器引擎（结构化数据编排）后端服务
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.infra.config import settings
from app.infra.database import get_db_manager
from app.api.v1.api import api_router
from app.api.auth import router as auth_router, get_current_user
from app.api.v1.endpoints.system import public_router as public_system_router


async def cron_scanner_loop():
    """
    自动巡逻循环：以「分钟」为单位读取 cron_interval_min，受 cron_enabled 开关控制。
    扫描完成后根据 auto_scrape / auto_subtitles 开关自动串联刮削和字幕任务。
    完整流水线：物理扫描 → 智能入库 → 刮削元数据 → 搜索字幕
    """
    default_interval_minutes = 60

    while True:
        try:
            db = get_db_manager()

            # ── 读取开关配置 ────────────────────────────────────────
            def _bool(val):
                return val not in (None, "", False, "false", "0")

            cron_enabled  = _bool(db.get_config("cron_enabled",  False))
            auto_scrape   = _bool(db.get_config("auto_scrape",   False))
            auto_subtitles= _bool(db.get_config("auto_subtitles",False))

            # ── 读取间隔配置 ────────────────────────────────────────
            raw = db.get_config("cron_interval_min", default_interval_minutes)
            try:
                interval_minutes = int(raw) if raw not in (None, "") else default_interval_minutes
            except (TypeError, ValueError):
                interval_minutes = default_interval_minutes
            if interval_minutes <= 0:
                interval_minutes = default_interval_minutes
            interval_seconds = interval_minutes * 60

            if not cron_enabled:
                print(f"[INFO] [CRON] cron_enabled=OFF，本轮跳过，{interval_minutes} 分钟后再检查")
                await asyncio.sleep(interval_seconds)
                continue

            # ── 步骤 1：物理扫描 + 智能入库 ────────────────────────
            print("[INFO] [CRON] ▶ 步骤1 开始物理扫描 + 智能入库...")
            from app.api.v1.endpoints.tasks import perform_scan_task
            await perform_scan_task()
            print("[OK]   [CRON] ✔ 步骤1 扫描完成")

            # ── 步骤 2：自动刮削（可选）────────────────────────────
            if auto_scrape:
                print("[INFO] [CRON] ▶ 步骤2 auto_scrape=ON，开始全量刮削...")
                from app.api.v1.endpoints.tasks import (
                    perform_scrape_all_task_sync,
                    scrape_all_status,
                )
                if scrape_all_status["is_running"]:
                    print("[WARN] [CRON] 刮削任务正在执行中，本轮跳过")
                else:
                    await asyncio.get_event_loop().run_in_executor(
                        None, perform_scrape_all_task_sync
                    )
                    print("[OK]   [CRON] ✔ 步骤2 刮削完成")

                # ── 步骤 3：自动字幕（可选，依赖刮削完成）──────────
                if auto_subtitles:
                    print("[INFO] [CRON] ▶ 步骤3 auto_subtitles=ON，开始搜索字幕...")
                    from app.api.v1.endpoints.tasks import (
                        perform_find_subtitles_task_sync,
                        find_subtitles_status,
                    )
                    if find_subtitles_status["is_running"]:
                        print("[WARN] [CRON] 字幕任务正在执行中，本轮跳过")
                    else:
                        await asyncio.get_event_loop().run_in_executor(
                            None, perform_find_subtitles_task_sync
                        )
                        print("[OK]   [CRON] ✔ 步骤3 字幕搜索完成")
                else:
                    print("[INFO] [CRON] auto_subtitles=OFF，跳过字幕步骤")
            else:
                print("[INFO] [CRON] auto_scrape=OFF，跳过刮削和字幕步骤")

            print(f"[INFO] [CRON] 本轮流水线结束，{interval_minutes} 分钟后执行下一轮")
            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            print("[STOP] [CRON] 自动巡逻循环已停止")
            break
        except Exception as e:
            print(f"[ERROR] [CRON] 巡逻循环异常: {e}")
            await asyncio.sleep(60)  # 失败后 60 秒重试


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    BASE_DIR = Path(__file__).resolve().parent.parent
    log_dir = BASE_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 初始化 Python 标准 logging 系统
    log_file = log_dir / "app.log"
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 清除已有的处理器（避免重复）
    root_logger.handlers.clear()
    
    # 创建 RotatingFileHandler（磁盘日志持久化）
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
        delay=True  # Windows 并发访问兼容
    )
    file_handler.setLevel(logging.INFO)
    
    # 创建 StreamHandler（终端输出）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 统一日志格式（必须与 system.py 的解析正则对齐）
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 注册处理器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    logging.info("=" * 60)
    logging.info(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    logging.info("=" * 60)
    logging.info(f"[OK] 磁盘日志已启用: {log_file}")

    print("=" * 60)
    print(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    print("=" * 60)
    
    # 初始化数据库
    db_manager = get_db_manager()
    logging.info("[OK] 数据库初始化完成 (WAL 模式 + 原子写入)")
    print("[OK] 数据库初始化完成 (WAL 模式 + 原子写入)")
    
    # 启动自动扫描循环
    cron_task = asyncio.create_task(cron_scanner_loop())
    logging.info("[OK] 自动扫描循环已启动")
    print("[OK] 自动扫描循环已启动")
    
    # 检查 Docker 统一挂载点
    if os.path.exists(settings.DOCKER_STORAGE_PATH):
        logging.info(f"[OK] Docker 影音挂载点已就绪: {settings.DOCKER_STORAGE_PATH}")
        print(f"[OK] Docker 影音挂载点已就绪: {settings.DOCKER_STORAGE_PATH}")
    else:
        logging.warning(f"[WARN] Docker 影音挂载点未找到: {settings.DOCKER_STORAGE_PATH}")
        print(f"[WARN] Docker 影音挂载点未找到: {settings.DOCKER_STORAGE_PATH}")
    
    logging.info(f"[INFO] API 文档地址: http://{settings.HOST}:{settings.PORT}/docs")
    print(f"[INFO] API 文档地址: http://{settings.HOST}:{settings.PORT}/docs")
    print("=" * 60)
    
    yield
    
    # 关闭时执行：取消自动扫描任务
    cron_task.cancel()
    try:
        await cron_task
    except asyncio.CancelledError:
        pass
    logging.info("[STOP] Neon Crate Server 正在关闭...")
    print("[STOP] Neon Crate Server 正在关闭...")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Neon Crate API Gateway",
    description="Quantum Data Container Orchestration Engine // 神经链路核心 API 接口库",
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 - 鉴权路由必须在最前面
app.include_router(auth_router, prefix="/api/v1/auth", tags=["Authentication"])

# 图片代理路由（需要 JWT 鉴权，防止未授权文件读取）
app.include_router(
    public_system_router,
    prefix=f"{settings.API_V1_PREFIX}/public",
    tags=["Public System"],
    dependencies=[Depends(get_current_user)]
)


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常捕获"""
    print(f"[ERROR] 未处理的异常: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"服务器内部错误: {str(exc)}",
            "data": None
        }
    )


@app.get("/health")
async def health_check():
    """健康检查端点（脱敏：不暴露版本号与时间戳）"""
    return {"status": "online"}


# 业务路由（全局 JWT 保护）
app.include_router(
    api_router, 
    prefix=settings.API_V1_PREFIX,
    dependencies=[Depends(get_current_user)]
)


# ==========================================
# 静态资源挂载：/storage -> /api/v1/assets
# ==========================================
# 优先使用 Docker 挂载点，Windows 环境自动回退到项目根目录下的 data/posters
assets_dir = None
if os.path.isdir(settings.DOCKER_STORAGE_PATH):
    assets_dir = settings.DOCKER_STORAGE_PATH
    print(f"[OK] 静态资源已挂载: {settings.DOCKER_STORAGE_PATH} -> /api/v1/assets")
else:
    # Windows 环境回退方案：使用项目根目录下的 data/posters
    fallback_dir = Path(__file__).resolve().parent.parent / "data" / "posters"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = str(fallback_dir)
    print(f"[OK] 静态资源已挂载（Windows 回退）: {assets_dir} -> /api/v1/assets")

if assets_dir:
    app.mount("/api/v1/assets", StaticFiles(directory=assets_dir), name="assets")


# ==========================================
# AIO 模式：挂载前端静态文件（可选）
# ==========================================
_frontend_static = "static"
if os.path.isdir(_frontend_static):
    app.mount("/", StaticFiles(directory=_frontend_static, html=True), name="frontend")
    print(f"[OK] 前端静态文件已挂载: {_frontend_static} -> /")
else:
    print(f"[INFO] 未找到前端静态目录 {_frontend_static}，AIO 模式未启用")


# ==========================================
# SPA 404 回退处理器（前端单页路由兼容）
# ==========================================
@app.exception_handler(404)
async def spa_fallback_handler(request, exc):
    """
    SPA 单页应用 404 回退：
    - 若为 API 请求（以 /api 开头）：返回 JSON 404
    - 其他所有请求：一律回退到 static/index.html，由前端路由接管
    """
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    
    # 检查 static/index.html 是否存在
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse("static/index.html")
    else:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})


if __name__ == "__main__":
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
