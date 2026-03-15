"""
应用生命周期管理 - 启动/关闭逻辑

设计模式：上下文管理器（asynccontextmanager）
- 管理应用的启动和关闭流程
- 确保资源正确初始化和清理
- 支持异步任务管理

核心职责：
1. 日志系统初始化（RotatingFileHandler，10MB 轮转）
2. 数据库初始化（WAL 模式，原子写入）
3. 孤儿任务清理（重置上次崩溃遗留的 pending 状态）
4. 自动扫描循环启动/停止（定时巡逻）
5. 环境检查（Docker 挂载点、配置文件等）

自动巡逻循环：
- 以分钟为单位读取 cron_interval_min
- 受 cron_enabled 开关控制
- 完整流水线：物理扫描 → 智能入库 → 刮削元数据 → 搜索字幕
- 支持 auto_scrape 和 auto_subtitles 开关

孤儿任务清理：
- 问题场景：进程崩溃导致任务卡在 pending 状态
- 解决方案：启动时重置所有孤儿任务
- 确保系统重启后任务队列干净
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

from app.infra.config import settings
from app.infra.database import get_db_manager


def _setup_logging() -> Path:
    """
    初始化日志系统（异步优化版）
    
    日志配置：
    - 文件日志：RotatingFileHandler（10MB 轮转，最多 5 个备份文件）
    - 控制台日志：StreamHandler（同步输出到终端）
    - 日志路径：data/logs/app.log（相对于项目根目录）
    - 日志级别：INFO（DEBUG 级别不记录到文件）
    - 日志格式：时间戳 - 模块名 - 级别 - 消息
    
    异步优化（新增）：
    - QueueHandler：主线程写入队列（非阻塞）
    - QueueListener：后台线程批量写入文件（异步）
    - 适合高频日志场景（压力测试：5000 条/10秒）
    
    为什么用 RotatingFileHandler？
    - 防止日志文件无限增长耗尽磁盘
    - 10MB 轮转：适合 NAS 等存储受限环境
    - 5 个备份：保留足够的历史日志
    
    Returns:
        Path: 日志文件路径
    """
    from logging.handlers import QueueHandler, QueueListener
    from queue import Queue
    
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    log_dir = BASE_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.handlers.clear()

    # 创建日志队列（异步写入，最多缓存 50000 条，防止高频刮削时丢日志）
    log_queue = Queue(maxsize=50000)
    
    # 创建 RotatingFileHandler（后台线程使用）
    file_handler = RotatingFileHandler(
        filename=str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
        delay=False  # 立即打开文件，不延迟
    )
    file_handler.setLevel(logging.INFO)

    # 创建 StreamHandler（控制台输出）
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 统一日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    formatter = logging.Formatter(log_format)
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 创建 QueueHandler（主线程使用，非阻塞）
    queue_handler = QueueHandler(log_queue)
    root_logger.addHandler(queue_handler)
    root_logger.addHandler(console_handler)

    # 创建 QueueListener（后台线程，批量写入）
    queue_listener = QueueListener(log_queue, file_handler, respect_handler_level=True)
    queue_listener.start()
    
    # 保存 listener 引用，供 shutdown 时停止
    root_logger._queue_listener = queue_listener

    logging.info("[OK] 日志系统已启动（异步队列模式）")
    return log_file


def _check_environment() -> None:
    """检查运行环境"""
    logging.info("=" * 60)
    logging.info(f"[START] {settings.APP_NAME} v{settings.APP_VERSION} 正在启动...")
    logging.info("=" * 60)

    # 检查 Docker 挂载点
    if os.path.exists(settings.DOCKER_STORAGE_PATH):
        logging.info(f"[OK] Docker 影音挂载点已就绪: {settings.DOCKER_STORAGE_PATH}")
    else:
        logging.warning(f"[WARN] Docker 影音挂载点未找到: {settings.DOCKER_STORAGE_PATH}")

    logging.info(f"[INFO] API 文档地址: http://{settings.HOST}:{settings.PORT}/docs")


async def _sqlite_maintenance():
    """SQLite 定期维护：WAL checkpoint + 碎片整理（每 24 轮 Cron 触发一次，约每天一次）"""
    try:
        from app.infra.database import get_db_manager
        db = get_db_manager()
        conn = db._get_conn()
        with db.db_lock:
            # 合并 .wal 到 .db，截断防止 .wal 膨胀
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            # 重建 .db，回收删除操作留下的空洞碎片
            conn.execute("VACUUM")
            # VACUUM 后优化查询分析器
            conn.execute("PRAGMA optimize")
            conn.commit()
        logging.info("[CRON] 🟢 SQLite 定期维护完成（WAL checkpoint + VACUUM）")
    except Exception as e:
        logging.warning(f"[CRON] 🟡 SQLite 维护失败（非致命）: {e}")


async def cron_scanner_loop():
    """
    自动巡逻循环 - 定时任务引擎
    
    设计目标：
    - 定期扫描新文件，实现媒体库自动更新
    - 串联刮削和字幕任务，实现全自动入库
    - 支持配置热更新，无需重启即可调整间隔
    
    完整流水线（3 个步骤，可按需开启）：
    
    步骤 1：物理扫描 + 智能入库（必须执行）
    - 扫描下载目录，发现新文件
    - inode 防重，避免重复入库
    - 失忆救援，恢复孤儿文件
    
    步骤 2：自动刮削（auto_scrape=ON 时执行）
    - 调用 TMDB API 获取元数据
    - 下载海报、Fanart
    - 生成 NFO 文件
    
    步骤 3：自动字幕（auto_subtitles=ON 且 auto_scrape=ON 时执行）
    - 调用 OpenSubtitles API 搜索字幕
    - 下载最佳匹配字幕
    - 依赖刮削步骤提供的 TMDB ID
    
    配置项：
    - cron_enabled：是否开启定时巡逻（默认关闭）
    - cron_interval_min：巡逻间隔（分钟，默认 60）
    - auto_scrape：是否自动刮削（默认关闭）
    - auto_subtitles：是否自动搜索字幕（默认关闭）
    
    错误处理：
    - 任意步骤失败不影响下一轮执行
    - 错误信息写入数据库，前端可查询
    - 失败后 60 秒重试
    """
    default_interval_minutes = 60
    _maintenance_loops = 0  # SQLite 定期维护计数器（每 24 轮触发一次）

    while True:
        try:
            db = get_db_manager()

            # ── 读取开关配置 ────────────────────────────────────────
            def _bool(val):
                return val not in (None, "", False, "false", "0")

            cron_enabled = _bool(db.get_config("cron_enabled", False))
            auto_scrape = _bool(db.get_config("auto_scrape", False))
            auto_subtitles = _bool(db.get_config("auto_subtitles", False))

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
                logging.debug(f"[CRON] cron_enabled=OFF，本轮跳过，{interval_minutes} 分钟后再检查")
                # 🚀 高敏心跳睡眠：10 秒一次浅睡眠，即时响应开关变更
                _sleep_chunk = 10
                _elapsed = 0
                while _elapsed < interval_seconds:
                    await asyncio.sleep(_sleep_chunk)
                    _elapsed += _sleep_chunk
                    try:
                        _still_enabled = get_db_manager().get_config("cron_enabled", False)
                        if str(_still_enabled).lower() in ("false", "0", "") or not _still_enabled:
                            pass  # 仍然关闭，继续等待
                        else:
                            logging.info("[CRON] ⚡ 侦测到定时巡逻已被开启，立即中止等待进入下一轮！")
                            break
                    except Exception:
                        pass
                continue

            # ── 步骤 1：物理扫描 + 智能入库 ────────────────────────
            logging.info("[CRON] ▶ 步骤1 开始物理扫描 + 智能入库...")
            from app.api.v1.endpoints.tasks import perform_scan_task_sync
            await asyncio.get_running_loop().run_in_executor(None, perform_scan_task_sync)
            logging.info("[CRON] ✔ 步骤1 扫描完成")

            # ── 步骤 2：自动刮削（可选）────────────────────────────
            if auto_scrape:
                logging.info("[CRON] ▶ 步骤2 auto_scrape=ON，开始全量刮削...")
                from app.api.v1.endpoints.tasks import (
                    perform_scrape_all_task_sync,
                    scrape_all_status,
                )
                if scrape_all_status["is_running"]:
                    logging.warning("[CRON] 刮削任务正在执行中，本轮跳过")
                else:
                    await asyncio.get_running_loop().run_in_executor(
                        None, perform_scrape_all_task_sync
                    )
                    logging.info("[CRON] ✔ 步骤2 刮削完成")

                # ── 步骤 3：自动字幕（可选，依赖刮削完成）──────────
                if auto_subtitles:
                    logging.info("[CRON] ▶ 步骤3 auto_subtitles=ON，开始搜索字幕...")
                    from app.api.v1.endpoints.tasks import (
                        perform_find_subtitles_task_sync,
                        find_subtitles_status,
                    )
                    if find_subtitles_status["is_running"]:
                        logging.warning("[CRON] 字幕任务正在执行中，本轮跳过")
                    else:
                        await asyncio.get_running_loop().run_in_executor(
                            None, perform_find_subtitles_task_sync
                        )
                        logging.info("[CRON] ✔ 步骤3 字幕搜索完成")
                else:
                    logging.debug("[CRON] auto_subtitles=OFF，跳过字幕步骤")
            else:
                logging.debug("[CRON] auto_scrape=OFF，跳过刮削和字幕步骤")

            # ── SQLite 定期维护（每 24 轮约 1 天触发一次）──────────
            _maintenance_loops += 1
            if _maintenance_loops >= 24:
                await _sqlite_maintenance()
                _maintenance_loops = 0

            logging.info(f"[CRON] 本轮流水线结束，{interval_minutes} 分钟后执行下一轮")
            # 🚀 高敏心跳睡眠：将漫长的睡眠切分为 10 秒一次的微小阻塞，确保即时响应前端配置变更
            _sleep_chunk = 10
            _elapsed = 0
            while _elapsed < interval_seconds:
                await asyncio.sleep(_sleep_chunk)
                _elapsed += _sleep_chunk
                try:
                    # 每次浅睡眠醒来，查一次配置有没有变动
                    _current_db = get_db_manager()

                    # 1. 检查开关是否被突然关掉
                    _is_still_enabled = _current_db.get_config("cron_enabled", False)
                    if str(_is_still_enabled).lower() in ("false", "0", "") or not _is_still_enabled:
                        logging.info("[CRON] ⚡ 侦测到定时巡逻已被关闭，立即中止当前睡眠！")
                        break  # 打断内部睡眠，回到外层大循环顶部重新挂起

                    # 2. 检查时间间隔是否被修改
                    _new_interval_min = int(_current_db.get_config("cron_interval_min", 60))
                    _new_interval_seconds = _new_interval_min * 60
                    if _new_interval_seconds != interval_seconds:
                        logging.info(
                            f"[CRON] ⚡ 侦测到巡逻间隔已由 {interval_seconds // 60} 分钟"
                            f"修改为 {_new_interval_min} 分钟，立即生效！"
                        )
                        break  # 打断内部睡眠，立刻用新间隔开启下一轮

                except Exception:
                    pass  # 忽略查询期间的瞬时异常，继续睡眠

        except asyncio.CancelledError:
            logging.info("[CRON] 自动巡逻循环已停止")
            break
        except Exception as e:
            error_msg = str(e)
            logging.error(f"[CRON] 巡逻循环异常: {error_msg}", exc_info=True)
            # 将错误信息保存到数据库，前端可定期查询
            try:
                db = get_db_manager()
                db.set_config("cron_last_error", error_msg)
                db.set_config("cron_last_error_time", datetime.now().isoformat())
            except Exception as db_err:
                logging.error(f"[CRON] 保存错误信息到数据库失败: {db_err}")
            await asyncio.sleep(60)  # 失败后 60 秒重试


@asynccontextmanager
async def lifespan(app):
    """
    应用生命周期管理

    Args:
        app: FastAPI 应用实例
    """
    # ── 启动时执行 ──────────────────────────────────────────────
    log_file = _setup_logging()
    logging.info(f"[OK] 磁盘日志已启用: {log_file}")

    _check_environment()

    # 初始化数据库
    db_manager = get_db_manager()
    logging.info("[OK] 数据库初始化完成 (WAL 模式 + 原子写入)")

    # Task G — 孤儿任务清理：将上次崩溃遗留的 is_running 状态重置
    # scrape_all_status / find_subtitles_status 是内存字典，进程重启后自动归零。
    # 但数据库中可能存在因崩溃卡在 pending 状态的孤儿任务，此处统一重置。
    try:
        from app.api.v1.endpoints.tasks._shared import scrape_all_status, find_subtitles_status
        scrape_all_status["is_running"] = False
        find_subtitles_status["is_running"] = False
        orphan_count = db_manager.reset_orphan_pending_tasks()
        if orphan_count:
            logging.warning(f"[STARTUP] 已将 {orphan_count} 个孤儿 pending 任务重置（上次崩溃遗留）")
        else:
            logging.info("[STARTUP] 无孤儿任务，数据库状态干净")
    except Exception as _orphan_err:
        logging.warning(f"[STARTUP] 孤儿任务重置失败（非致命）: {_orphan_err}")

    # 启动自动扫描循环
    cron_task = asyncio.create_task(cron_scanner_loop())
    logging.info("[OK] 自动扫描循环已启动")

    logging.info("=" * 60)

    yield

    # ── 关闭时执行 ──────────────────────────────────────────────
    cron_task.cancel()
    try:
        await cron_task
    except asyncio.CancelledError:
        pass
    
    # 关闭日志队列监听器（新增）
    root_logger = logging.getLogger()
    if hasattr(root_logger, '_queue_listener'):
        root_logger._queue_listener.stop()
        logging.info("[OK] 日志队列监听器已停止")
    
    logging.info("[STOP] Neon Crate Server 正在关闭...")
