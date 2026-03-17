"""
subtitle_task.py - 字幕补完任务

包含：
1. perform_find_subtitles_task_sync() — 同步字幕执行函数（线程池运行）
2. trigger_find_subtitles() — POST /find_subtitles 路由
3. get_find_subtitles_status() — GET /find_subtitles/status 路由
"""
import asyncio
import glob
import os
import re
import time
import logging
import threading
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.infra.constants import VALID_SUB_EXTS


def _check_local_subtitles(video_path: str) -> bool:
    """
    检查视频同级目录下是否存在字幕文件（支持极致模糊匹配）
    
    设计目标：
    - 避免重复下载已有的字幕
    - 支持多种字幕命名规范
    - 兼容手动添加的字幕文件
    
    检测策略（三级匹配）：
    
    1. 严格匹配（精确匹配）：
       - 格式：视频文件名.字幕扩展名
       - 例如：The.Matrix.1999.mkv → The.Matrix.1999.srt
       - 适用：标准命名的字幕
    
    2. 通配匹配（多语言字幕）：
       - 格式：视频文件名.*.字幕扩展名
       - 例如：The.Matrix.1999.mkv → The.Matrix.1999.zh-CN.srt
       - 适用：带语言代码的字幕
    
    3. 终极模糊匹配（宽松匹配）：
       - 剧集：只要字幕名包含同样的季集号（如 S01E01）就放行
       - 电影：同目录下只要有任何字幕文件，直接放行
       - 适用：命名不规范的字幕、手动添加的字幕
    
    支持的字幕格式：
    - .srt（SubRip，最常见）
    - .ass（Advanced SubStation Alpha，支持特效）
    - .vtt（WebVTT，网页字幕）
    - .sub/.idx（VobSub，DVD 字幕）
    
    Args:
        video_path: 视频文件路径
    
    Returns:
        True: 存在字幕文件
        False: 不存在字幕文件
    """
    if not video_path or not os.path.exists(video_path):
        return False
    dir_name = os.path.dirname(video_path)
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    valid_exts = VALID_SUB_EXTS
    
    # 1. 严格与通配匹配 (原有逻辑)
    for ext in valid_exts:
        if os.path.exists(os.path.join(dir_name, f"{base_name}{ext}")):
            return True
        if glob.glob(os.path.join(glob.escape(dir_name), f"{glob.escape(base_name)}.*{ext}")):
            return True

    # 2. 终极模糊匹配（只要有字幕文件就算过）
    try:
        episode_match = re.search(r'(S\d+E\d+)', base_name, re.IGNORECASE)
        for file in os.listdir(dir_name):
            if os.path.splitext(file)[1].lower() in valid_exts:
                if episode_match:
                    # 剧集：只要字幕名包含同样的季集号 (如 S01E01) 就放行
                    if episode_match.group(1).lower() in file.lower():
                        return True
                else:
                    # 电影：同目录下只要有任何字幕文件，直接放行
                    return True
    except Exception:
        pass
    return False

from app.infra.database import get_db_manager
from app.models.domain_media import ScanResponse
from app.api.v1.endpoints.tasks._shared import find_subtitles_status

logger = logging.getLogger(__name__)
router = APIRouter()

# 🚀 物理级并发防重锁：防止前端快速连点触发多个字幕任务同时运行。
# 设计选择：使用 threading.Lock 而非 asyncio.Lock，因为任务在同步线程池中执行。
_subtitle_entry_lock = threading.Lock()


# ==========================================
# 字幕任务执行函数
# ==========================================

def perform_find_subtitles_task_sync():
    """
    执行全量字幕补完任务（同步版本，用于线程池执行）
    
    核心流程：
    1. 获取待字幕任务 -> 2. 本地字幕白嫖（已有字幕直接跳过）-> 3. 调用 OpenSubtitles API
    -> 4. AI 命名规范重命名 -> 5. 写回数据库状态 -> 6. 遵守频率限制休眠 5 秒防封号
    
    字幕白嫖前置拦截（支持格式：.srt/.ass/.vtt/.sub/.idx）：
    1. 严格匹配：视频文件名 + 字幕扩展名 -> 2. 通配匹配：文件名.*.srt（多语言）
    -> 3. 模糊匹配：同目录任意字幕（电影）或季集号匹配（剧集）
    
    AI 命名规范后处理：
    1. 读取原始文件名（如 movie.srt）-> 2. 重命名为「视频名.ai.语言码.扩展名」标准格式
    -> 3. 语言代码：zh-CN（简体）/ zh-TW（繁体）/ en（英文）
    
    频率限制保护：
    1. 每个任务完成后强制休眠 5 秒 -> 2. 遵守 OpenSubtitles 每秒最多 1 请求限制
    -> 3. 防止因高频调用导致账号被封
    """
    global find_subtitles_status

    # ── 并发锁释放核安全（DO NOT MODIFY）──────────────────────────────
    # 🚨 架构师警告 (DO NOT MODIFY): 核安全边界，改动极易引发死锁或路径穿越。
    # - 本任务在同步线程池中运行；必须使用 `threading.Lock` 做物理并发短路。
    # - 无论发生何种异常，都必须走到 finally，确保：
    #   1) `find_subtitles_status["is_running"] = False`
    #   2) 释放 `_subtitle_entry_lock`（且仅在持锁时释放，避免 RuntimeError 反向破坏自愈链路）
    #
    # 🚀 物理级并发防重逻辑：
    # 1. 尝试非阻塞获取锁（blocking=False），若锁已被占用则立即返回，不排队、不等待，直接丢弃冗余请求。
    # 2. 检查内存状态标记位 is_running，确保逻辑与物理锁状态同步（双重防护）。
    # 3. 任务执行完毕后在 finally 块中释放锁，确保即使任务崩溃系统也能自愈。
    if not _subtitle_entry_lock.acquire(blocking=False):
        logger.warning("[SUBTITLE] ⚠️ 拦截并发请求：已有字幕任务正在运行中，本次触发已丢弃。")
        return

    try:
        if find_subtitles_status["is_running"]:
            return

        find_subtitles_status["is_running"] = True
        find_subtitles_status["error"] = None

        logger.info("[API] 开始查找字幕任务（线程池模式）...")

        db = get_db_manager()

        # 获取待字幕任务
        tasks_to_sub = db.get_tasks_needing_subtitles()
        count = len(tasks_to_sub)

        if count == 0:
            logger.info("[API] 没有待处理的字幕任务")
            find_subtitles_status["is_running"] = False
            find_subtitles_status["processed_count"] = 0
            find_subtitles_status["last_run_time"] = time.time()
            return

        # 获取 OpenSubtitles API 配置
        api_key = db.get_config("os_api_key", "").strip()
        user_agent = db.get_config("os_user_agent", "SubtitleHunter v13.2")

        if not api_key:
            logger.warning("[API] 未配置 OpenSubtitles API Key，跳过字幕任务")
            find_subtitles_status["error"] = "未配置 OpenSubtitles API Key"
            return

        # 初始化字幕引擎
        from app.services.subtitle import SubtitleEngine
        from app.services.subtitle.engine import SubtitleFatalError
        subtitle_engine = SubtitleEngine(api_key=api_key, user_agent=user_agent)

        # 使用 asyncio.run() 在独立线程中创建隔离事件循环（Python 3.10+ 推荐方式）
        # 避免 get_event_loop() 废弃警告与嵌套 loop 死锁风险

        # 逐个处理任务
        processed = 0
        for task in tasks_to_sub:
            try:
                file_path = task.get("path")
                tmdb_id = task.get("tmdb_id")
                imdb_id = task.get("imdb_id")
                media_type = task.get("type", "movie")
                target_path = task.get("target_path")
                _is_arc = task.get("is_archive", False)
                _task_id = task.get("id")

                # ==========================================
                # 🎁 字幕白嫖前置拦截（Local Subtitle Detection）
                # ==========================================
                # 设计目标：避免重复下载已有的字幕
                # 
                # 检测时机：在调用 OpenSubtitles API 之前
                # 检测路径：优先检查 target_path（媒体库），回退到 file_path（下载目录）
                # 
                # 优势：
                # - 零 API 消耗：无需调用 OpenSubtitles API
                # - 零网络延迟：无需等待 API 响应
                # - 支持手动字幕：用户自行添加的字幕也能识别
                # 
                # 状态更新：
                # - 发现字幕：标记为 success，不再进入字幕队列
                # - 未发现字幕：继续执行下载流程
                # ==========================================
                _sub_path = target_path or file_path
                if _sub_path and _check_local_subtitles(_sub_path):
                    logger.info(f"[SUBTITLE] [白嫖] 发现本地字幕，跳过下载 -> {_sub_path}")
                    if _task_id:
                        db.update_any_task_metadata(_task_id, _is_arc, sub_status="success")
                    processed += 1
                    continue

                # 无 tmdb_id 时降级为文件名搜索（不直接跳过）
                if not file_path:
                    logger.warning(f"[SUBTITLE] 任务缺少 file_path，跳过: {_task_id}")
                    continue
                if not tmdb_id:
                    logger.info(f"[SUBTITLE] 任务无 tmdb_id，降级为文件名搜索: {file_path}")

                logger.info(f"[SUBTITLE] 处理任务: {file_path}")

                # 调用字幕下载（使用事件循环驱动协程）
                result = asyncio.run(subtitle_engine.download_subtitle_for_task(
                    db_manager=db,
                    file_path=file_path,
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    imdb_id=imdb_id,
                    target_path=target_path,
                    archive_id=task.get("id") if _is_arc else None
                ))

                logger.info(f"[SUBTITLE] 结果: {result}")

                # ==========================================
                # 🚀 AI 命名规范后处理（Subtitle Naming Convention）
                # ==========================================
                # 设计目标：将字幕引擎下载的字幕重命名为标准格式
                # 
                # 原始格式：
                # - OpenSubtitles 返回的文件名（如 movie.srt、subtitle.ass）
                # - 不规范，难以识别语言和来源
                # 
                # 标准格式：
                # - 视频文件名.ai.语言代码.扩展名
                # - 例如：The.Matrix.1999.ai.zh-CN.srt
                # - 符合 Plex/Jellyfin/Emby 命名规范
                # 
                # 语言代码：
                # - zh-CN：简体中文
                # - zh-TW：繁体中文
                # - en：英文
                # 
                # AI 标记：
                # - .ai. 前缀标识这是 AI 系统下载的字幕
                # - 区别于用户手动添加的字幕
                # - 便于后续管理和清理
                # ==========================================
                if target_path and result and result.startswith("成功:"):
                    # 双表感知写回字幕状态
                    if _task_id:
                        db.update_any_task_metadata(_task_id, _is_arc, sub_status="success")

                processed += 1

                # ==========================================
                # 🛡️ 严格防封号（API Rate Limit Protection）
                # ==========================================
                # OpenSubtitles API 频率限制：
                # - 免费账号：每秒最多 1 个请求
                # - 付费账号：每秒最多 5 个请求
                # 
                # 保护策略：
                # - 单线程执行：不使用并发，避免触发限流
                # - 任务间隔：每个任务完成后休眠 5 秒
                # - 重试机制：遇到 429 限流时自动等待并重试
                # 
                # 为什么是 5 秒？
                # - 留出安全余量：避免边界情况触发限流
                # - 兼容付费账号：付费用户可以手动调整间隔
                # - 防止封号：严格遵守 API 使用规范
                # ==========================================
                logger.info("[SUBTITLE] 遵守字幕 API 频率限制，单线程休眠 5 秒...")
                time.sleep(5)

            except SubtitleFatalError as e:
                logger.error(
                    f"[SUBTITLE] 🛑 触发全局熔断: {e}，"
                    f"直接跳过剩余任务，已处理 {processed}/{count} 个！"
                )
                find_subtitles_status["error"] = f"熔断: {e}"
                break  # 立刻退出循环，不再处理任何任务
            except Exception as e:
                logger.error(f"[SUBTITLE] 处理任务失败: {str(e)}")
                continue

        find_subtitles_status["processed_count"] = processed
        find_subtitles_status["last_run_time"] = time.time()

        logger.info(f"[API] 查找字幕完成，已处理 {processed}/{count} 个任务")

    except Exception as e:
        find_subtitles_status["error"] = str(e)
        logger.error(f"[API] 查找字幕执行失败: {str(e)}")

    finally:
        # 🚀 物理级并发防重逻辑 — 步骤 3：
        # 无论任务正常结束、抛出异常还是遭遇 BaseException，finally 块确保：
        # - is_running 复位为 False，解除前端「运行中」UI 锁定
        # - 释放 threading.Lock，允许下一次任务进入，实现系统自愈
        find_subtitles_status["is_running"] = False
        # 防御性释放：避免重复 release 导致 RuntimeError，反向破坏 finally 的“最后一公里”
        if _subtitle_entry_lock.locked():
            _subtitle_entry_lock.release()


# ==========================================
# 路由端点
# ==========================================

@router.post("/find_subtitles", response_model=ScanResponse)
async def trigger_find_subtitles(background_tasks: BackgroundTasks):
    """
    触发全量字幕补完任务（后台线程执行，快速返回）。

    业务链路：
    查询待字幕任务 → 本地字幕存在性短路（白嫖拦截）→ OpenSubtitles 检索/下载 → AI 命名规范重命名 → 写回字幕状态与计数。

    Args:
        background_tasks: FastAPI 后台任务容器。内部会将同步逻辑封装进线程执行，避免阻塞事件循环。

    Returns:
        ScanResponse: 立即返回“已启动/运行中”的确认消息；真实进度通过 `GET /find_subtitles/status` 轮询。

    Raises:
        HTTPException:
            - 500: 后台任务投递失败或运行时异常。
    """
    global find_subtitles_status

    if find_subtitles_status["is_running"]:
        logger.warning("[API] 查找字幕任务已在运行中")
        return ScanResponse(message="查找字幕任务已在运行中，请稍后再试")

    try:
        # 将阻塞的同步任务包装到独立线程中运行，避免阻塞事件循环
        async def run_sub_in_thread():
            await asyncio.to_thread(perform_find_subtitles_task_sync)

        background_tasks.add_task(run_sub_in_thread)
        logger.info("[API] 查找字幕任务已加入后台线程队列")
        return ScanResponse(message="查找字幕任务已启动，正在后台线程执行")
    except Exception as e:
        logger.error(f"[API] 启动查找字幕失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动查找字幕失败: {str(e)}")


@router.get("/find_subtitles/status")
async def get_find_subtitles_status() -> Dict[str, Any]:
    """
    获取字幕补完任务状态（用于前端轮询渲染运行态）。

    业务链路：
    只读返回内存态 `find_subtitles_status`，用于 UI 展示与按钮态控制；不触发外部 API 调用。

    Returns:
        Dict[str, Any]:
            - is_running: 是否正在运行
            - last_run_time: 上次运行时间（Unix 时间戳）
            - processed_count: 已处理的任务数量
            - error: 错误信息（若有）
    """
    return {
        "is_running": find_subtitles_status["is_running"],
        "last_run_time": find_subtitles_status["last_run_time"],
        "processed_count": find_subtitles_status["processed_count"],
        "error": find_subtitles_status["error"]
    }
