"""
scrape_task.py - 全量刮削任务

包含：
1. perform_scrape_all_task_sync() — 同步刮削执行函数（线程池运行）
2. trigger_scrape_all() — POST /scrape_all 路由
"""
import os
import re
import shutil
import glob
import asyncio
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.infra.database import get_db_manager
from app.models.domain_media import ScanResponse
from app.services.organizer.hardlinker import SmartLink
from app.services.metadata.metadata_manager import MetadataManager
from app.api.v1.endpoints.tasks._shared import (
    scrape_all_status,
    _update_library_counts,
)


def _check_local_subtitles(video_path: str, sub_exts: frozenset = None) -> bool:
    """检查视频同级目录下是否存在字幕文件（支持极致模糊匹配）"""
    if not video_path or not os.path.exists(video_path):
        return False
    dir_name = os.path.dirname(video_path)
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    valid_exts = sub_exts if sub_exts else frozenset({'.srt', '.ass', '.vtt', '.sub', '.idx'})
    
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
    except Exception as e:
        logger.debug(f"[SUBTITLE] 模糊匹配检测出现异常 (可忽略): {e}")
    return False
logger = logging.getLogger(__name__)
router = APIRouter()

# 🚀 物理级并发防重锁：防止前端快速连点触发多个刮削任务同时运行。
# 设计选择：使用 threading.Lock 而非 asyncio.Lock，因为任务在同步线程池中执行。
_scrape_entry_lock = threading.Lock()


# ==========================================
# 刮削任务执行函数
# ==========================================

def perform_scrape_all_task_sync():
    """
    执行全量刮削任务（同步版本，用于线程池执行）
    
    ── 业务链路总览 ──
    1. 获取防重锁（非阻塞）-> 2. 检查 TMDB API Key -> 3. 获取待刮削任务列表 -> 
    4. 初始化刮削器和 AI Agent -> 5. 逐个处理任务（NFO 短路 → AI 提炼 → TMDB 搜索 → 防重拦截 → 就地补录 → 归档全链路 → 字幕白嫖）-> 
    6. 更新统计信息 -> 7. 释放防重锁
    """
    # ── 防重锁获取（物理级并发防护）──
    # 业务链路：1. 尝试非阻塞获取锁（blocking=False）-> 2. 若锁已被占用则立即返回（不排队、不等待）-> 
    # 3. 丢弃冗余请求，防止并发刮削
    # 🚀 物理级并发防重逻辑：
    # 1. 尝试非阻塞获取锁（blocking=False），若锁已被占用则立即返回，不排队、不等待，直接丢弃冗余请求。
    # 2. 检查内存状态标记位 is_running，确保逻辑与物理锁状态同步（双重防护）。
    # 3. 任务执行完毕后在 finally 块中释放锁，确保即使任务崩溃系统也能自愈。
    if not _scrape_entry_lock.acquire(blocking=False):
        logger.warning("[SCRAPE] ⚠️ 拦截并发请求：已有刮削任务正在运行中，本次触发已丢弃。")
        return

    # ── Action 3: 修复双重检查锁定陷阱 ──
    # 在物理锁保护下再次检查 is_running，防止极端竞态窗口
    # （两个线程同时通过 acquire 前的状态检查，但只有一个能拿到锁）
    if scrape_all_status["is_running"]:
        _scrape_entry_lock.release()
        logger.warning("[SCRAPE] ⚠️ 锁内二次检查拦截：状态仍为 running，释放锁并退出。")
        return

    try:
        scrape_all_status["is_running"] = True
        scrape_all_status["error"] = None

        logger.info("[TMDB] 开始全量刮削任务（线程池模式）...")

        db = get_db_manager()

        # ── Step 2: 前置检查 TMDB API Key ──
        # 业务链路：1. 读取 TMDB API Key 配置 -> 2. 校验非空 -> 3. 若缺失则记录错误并返回
        tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
        if not tmdb_api_key:
            error_msg = "[TMDB] 错误：未配置 API Key，请前往设置页面填写"
            logger.error(error_msg)
            scrape_all_status["error"] = "未配置 TMDB API Key"
            return

        # ── Step 3: 读取多语言偏好配置 ──
        # 业务链路：1. 读取海报刮削语言 -> 2. 读取重命名语言 -> 3. 记录配置信息
        poster_lang = db.get_config("poster_lang", "zh")
        rename_lang = db.get_config("rename_lang", "zh")
        logger.info(f"[CONFIG] 海报刮削语言: {poster_lang}, 重命名语言: {rename_lang}")

        # ── Step 4: 获取待刮削任务列表 ──
        # 业务链路：1. 查询双表（热表 + 冷表）-> 2. 过滤条件：pending 或 archived 缺 imdb_id -> 
        # 3. 返回任务列表
        tasks_to_scrape = db.get_tasks_needing_scrape()
        count = len(tasks_to_scrape)

        logger.info(f"[TMDB] 发现 {count} 个待刮削任务")

        if count == 0:
            logger.info("[TMDB] 没有待处理的刮削任务")
            import time
            scrape_all_status["is_running"] = False
            scrape_all_status["processed_count"] = 0
            scrape_all_status["last_run_time"] = time.time()
            return

        # ── Step 5: 初始化刮削器和 AI Agent ──
        # 业务链路：1. 导入 TMDBAdapter 和 AIAgent -> 2. 创建刮削器实例 -> 3. 创建 AI Agent 实例
        from app.services.metadata.adapters import TMDBAdapter
        from app.services.ai.agent import AIAgent

        scraper = TMDBAdapter(api_key=tmdb_api_key, rename_lang=rename_lang, poster_lang=poster_lang)
        ai_agent = AIAgent(db)

        logger.info("[AI] AI 决策层已激活，将对所有文件名进行智能提炼")

        # 逐个处理任务
        processed = 0
        success_count = 0
        failed_count = 0

        for task in tasks_to_scrape:
            is_success, is_failed = _process_single_task(
                db=db,
                scraper=scraper,
                ai_agent=ai_agent,
                rename_lang=rename_lang,
                poster_lang=poster_lang,
                tmdb_api_key=tmdb_api_key,
                task=task,
            )
            if is_success:
                success_count += 1
            if is_failed:
                failed_count += 1
            processed += 1

        _update_library_counts()

        import time
        scrape_all_status["is_running"] = False
        scrape_all_status["processed_count"] = processed
        scrape_all_status["last_run_time"] = time.time()

        logger.info(f"[TMDB] 全量刮削完成，已处理 {processed}/{count} 个任务（成功: {success_count}, 失败: {failed_count})")

    except Exception as e:
        scrape_all_status["error"] = str(e)
        logger.error(f"[TMDB] 全量刮削执行失败: {str(e)}")
        try:
            db = get_db_manager()
            orphan_tasks = db.get_tasks_needing_scrape()
            for orphan in orphan_tasks:
                db.update_task_status(orphan["id"], "failed")
            if orphan_tasks:
                logger.error(f"[TMDB] 已将 {len(orphan_tasks)} 个孤儿 pending 任务标记为 failed")
        except Exception as rescue_err:
            logger.error(f"[TMDB] 孤儿任务救援失败: {rescue_err}")

    finally:
        # 无论任何情况（含 BaseException）都强制解锁，防止按钮永久僵死
        scrape_all_status["is_running"] = False
        # 🚀 物理级并发防重逻辑 — 步骤 3：
        # 无论任务正常结束、抛出异常还是遭遇 BaseException，finally 块确保：
        # - is_running 复位为 False，解除前端「运行中」UI 锁定
        # - 释放 threading.Lock，允许下一次任务进入，实现系统自愈
        _scrape_entry_lock.release()


def _step_nfo_shortcut(db, task: dict, file_path: str, task_id, clean_name: str) -> bool:
    """
    原子步骤 1: NFO 短路拦截（双轨隔离 — 自动刮削轨）

    业务链路：1. 查找本地 NFO 文件 -> 2. 解析 NFO 获取 TMDB ID / IMDb ID ->
    3. 若成功则跳过 AI 提炼和 TMDB 搜索 -> 4. 直接更新 DB 并归档 ->
    5. 若失败则降级走正常刮削流程
    由 nfo_parser.py 提供全兼容解析（Neon + TMM 3.1.x）
    绝对禁止调用 AI Agent 和 TMDB 搜索

    Returns:
        True  — 拦截成功，主流程应直接 return True, False
        False — 拦截未命中，降级走正常刮削流程
    """
    if not file_path:
        return False
    from app.services.metadata.nfo_parser import find_nfo, parse_nfo as _parse_nfo
    _nfo_path = find_nfo(file_path)
    if not _nfo_path:
        return False
    try:
        _nfo = _parse_nfo(_nfo_path)
        _nfo_tmdb_id = _nfo.get("tmdb_id")
        _nfo_imdb_id = _nfo.get("imdb_id") or ""
        _nfo_title   = _nfo.get("title") or ""
        _nfo_year    = _nfo.get("year") or ""
        if not _nfo_tmdb_id:
            return False
        logger.info(
            f"[NFO] 短路拦截成功: task={task_id}, "
            f"title='{_nfo_title}', tmdb={_nfo_tmdb_id}, imdb={_nfo_imdb_id}"
        )
        # 检查同目录海报
        _nfo_dir = str(Path(_nfo_path).parent)
        _nfo_poster = None
        for _pn in ["poster.jpg", "poster.png"]:
            _pc = os.path.join(_nfo_dir, _pn)
            if os.path.exists(_pc):
                _nfo_poster = _pc
                break
        _has_sub = _check_local_subtitles(
            file_path,
            sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))
        )
        # 短路分支属于“终态闭环”路径：避免 pending 泄漏导致无限跳过循环
        _sub_status = "success"
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(
            task_id, _is_arc,
            imdb_id=_nfo_imdb_id,
            tmdb_id=_nfo_tmdb_id,
            title=_nfo_title or clean_name,
            year=_nfo_year or None,
            sub_status=_sub_status
        )
        # 热表任务需调用 update_task_status 触发归档
        if not _is_arc:
            # is_active 默认 1，但此处强制回写确保状态机闭环（防止历史数据被手动停用后永远 pending）
            try:
                db.update_task_is_active(task_id, 1)
            except Exception:
                pass
            db.update_task_title_year(
                task_id=task_id,
                title=_nfo_title or clean_name,
                year=_nfo_year or None,
                season=task.get("season") if task.get("type") == "tv" else None
            )
            db.update_task_status(
                task_id=task_id,
                status="archived",
                tmdb_id=int(_nfo_tmdb_id),
                imdb_id=_nfo_imdb_id,
                target_path=file_path,
                sub_status=_sub_status,
                local_poster_path=_nfo_poster,
                task_type=task.get("type", "movie")
            )
        return True
    except Exception as _nfo_err:
        logger.warning(f"[NFO] 解析失败，降级走正常刮削流程: {_nfo_err}")
        return False


def _step_ai_extraction(
    db,
    ai_agent,
    task: dict,
    task_id,
    file_name: str,
    file_path: str,
    clean_name: str,
    media_type: str,
) -> tuple:
    """
    原子步骤 2: AI 提炼（文件名清理 + AI 识别 + 路径权威判断）

    业务链路：1. 调用 AI Agent 分析文件名 -> 2. 提取查询词、年份、类型 ->
    3. 若 AI 失败则降级使用正则清洗名 -> 4. 路径权威优先（不被 AI 覆盖）->
    5. 年份物理验证（防止 AI 推断错误年份）

    Returns:
        (refined_query, refined_year, refined_type)
    """
    raw_filename = file_name or file_path.split('\\')[-1].split('/')[-1]
    from app.services.scraper.cleaner import MediaCleaner as _MC
    cleaned_filename = _MC(db_manager=db).clean_name(raw_filename)
    if not cleaned_filename:
        cleaned_filename = raw_filename
    logger.info(f"[RegexLab] 物理正则去噪完成: '{raw_filename}' -> '{cleaned_filename}'")

    # 业务链路：1. 调用 AI Agent 分析文件名 -> 2. 提取查询词、年份、类型
    logger.info(f"[AI] 调用 AI Agent 分析文件名: {cleaned_filename}")
    try:
        # 1. 异步调用 AI Agent 进行媒体识别
        ai_result = asyncio.run(ai_agent.ai_identify_media(
            cleaned_name=cleaned_filename,
            full_path=file_path,
            type_hint=media_type
        ))
    except Exception as ai_err:
        logger.error(f"[AI] 识别异常: {ai_err}")
        ai_result = None

    # 2. AI 失败降级处理
    if not ai_result or not isinstance(ai_result, dict):
        _fallback_query = (cleaned_filename or clean_name or file_name or "").strip()
        logger.warning(
            f"[AI][FALLBACK] AI 分析返回 None 或非字典，任务 {task_id} 降级使用 "
            f"正则清洗名='{_fallback_query}' + db_type='{media_type}'"
        )
        ai_result = {"query": _fallback_query, "type": media_type, "filename_year": "", "knowledge_year": ""}

    # ── 路径权威优先：路径已定类型不被 AI 覆盖 ──
    # 业务链路：1. 读取 AI 建议的类型 -> 2. 若路径已定类型则强制使用路径类型 ->
    # 3. 若路径类型为空则使用 AI 建议 -> 4. 若 AI 建议非法则降级为 movie
    ai_suggested_type = (ai_result.get("type") or "").strip().lower()
    if media_type in ("movie", "tv"):
        refined_type = media_type
        if ai_suggested_type and ai_suggested_type != media_type:
            logger.info(
                f"[AI][PATH_AUTHORITY] 任务 {task_id}: AI 建议 type='{ai_suggested_type}' "
                f"被路径权威覆盖，强制使用 db_type='{media_type}'"
            )
    else:
        if ai_suggested_type in ("movie", "tv"):
            refined_type = ai_suggested_type
        else:
            refined_type = "movie"
            logger.warning(
                f"[AI][FALLBACK] 任务 {task_id}: AI 返回非法 type='{ai_suggested_type}'，"
                f"db_type 为空，最终降级为 'movie'"
            )

    # ── 搜索词校验 ──
    # 业务链路：1. 读取 AI 返回的查询词 -> 2. 若为空则降级使用 clean_name ->
    # 3. 记录最终使用的查询词
    refined_query = (ai_result.get("query") or "").strip()
    if not refined_query:
        refined_query = (clean_name or file_name or "").strip()
        logger.warning(
            f"[AI][FALLBACK] 任务 {task_id}: AI 返回空 query，"
            f"降级使用 clean_name='{refined_query}'"
        )

    # ── YEAR_MIRROR：6字段证据模型镜像校验 ────────────────────────────
    # 从 AI 返回的两个证据字段中提取年份（旧模型不返回时默认空字符串，静默兼容）
    filename_year  = (ai_result.get("filename_year")  or "").strip()
    knowledge_year = (ai_result.get("knowledge_year") or "").strip()

    if refined_type == "movie":
        if filename_year and knowledge_year and filename_year == knowledge_year:
            # 两份证据一致 → 精确过滤
            final_year = filename_year
            logger.info(
                f"[YEAR_MIRROR] 任务 {task_id}: 年份校验通过 "
                f"(文件:{filename_year} == 知识库:{knowledge_year})，使用年份过滤。"
            )
        elif filename_year and knowledge_year and filename_year != knowledge_year:
            # 两份证据冲突 → 置空，执行模糊搜索
            final_year = ""
            logger.warning(
                f"[YEAR_MIRROR] 冲突拦截：文件({filename_year}) vs 知识库({knowledge_year})，"
                f"已执行置空模糊搜索。task_id={task_id}, file='{raw_filename}'"
            )
        elif not filename_year and knowledge_year:
            # 单证据：仅知识库有值 → 直接使用知识库年份
            final_year = knowledge_year
            logger.info(
                f"[YEAR_MIRROR] 任务 {task_id}: 文件名无年份，"
                f"单证据使用知识库年份={knowledge_year}。"
            )
        else:
            # 两份证据均为空（或仅文件名有值而知识库为空）→ 模糊搜索
            final_year = filename_year if filename_year else ""
            logger.debug(
                f"[YEAR_MIRROR] 任务 {task_id}: 证据不足，"
                f"final_year='{final_year}'，执行模糊搜索。"
            )
    else:
        # TV：强制使用 knowledge_year（第一季首播年），忽略文件名年份
        final_year = knowledge_year
        if filename_year and knowledge_year and filename_year != knowledge_year:
            logger.info(
                f"[YEAR_MIRROR] 任务 {task_id}: TV 首播年对齐 "
                f"(文件:{filename_year} → 知识库首播年:{knowledge_year})。"
            )
    # ── YEAR_MIRROR 结束 ──────────────────────────────────────────────

    refined_year = final_year

    logger.info(
        f"[AI] 识别完成: query='{refined_query}' | final_year='{refined_year}' | "
        f"type='{refined_type}' | filename_year='{filename_year}' | "
        f"knowledge_year='{knowledge_year}' (db_type='{media_type}')"
    )
    return refined_query, refined_year, refined_type


def _step_tmdb_search_and_dup_check(
    db,
    scraper,
    task: dict,
    task_id,
    refined_query: str,
    refined_year: str,
    refined_type: str,
    rename_lang: str,
) -> dict | None:
    """
    原子步骤 3: TMDB 搜索与防重拦截

    业务链路：1. 根据类型调用 TMDB 搜索 -> 2. 若剧集搜索失败则二次搜索（去集号）->
    3. 精确匹配或宽松匹配候选结果 -> 4. 提取 TMDB ID、标题、年份

    Returns:
        dict — 包含 tmdb_id/title/year/imdb_id/season_num/episode_num 的结果字典
        None — 未找到结果或被判定为重复/ignored（已写库），主流程应 return False, True
    """
    # ── TMDB 搜索与防重拦截 ──
    # 业务链路：1. 根据类型调用 TMDB 搜索 -> 2. 若剧集搜索失败则二次搜索（去集号）->
    # 3. 精确匹配或宽松匹配候选结果 -> 4. 提取 TMDB ID、标题、年份
    if refined_type == "movie":
        results = scraper.search_movie(query=refined_query, year=refined_year)
    else:
        results = scraper.search_tv(query=refined_query, year=refined_year)

    # ── 三梯队搜索降级策略 ──────────────────────────────────────────
    # 第一梯队（精确）：Title + Year（已在上方执行）
    # 第二梯队（容错）：Title 完整片名，移除 Year（AI 幻觉年份时拯救正确片名）
    # 第三梯队（模糊）：截断片名第一段，无 Year（最后手段）
    if (not results or len(results) == 0) and refined_type == "tv" and refined_year:
        # 第二梯队：保留完整片名，移除年份限定
        logger.info(f"[TMDB] 剧集匹配失败（第一梯队），第二梯队：完整片名无年份搜索: '{refined_query}'")
        results = scraper.search_tv(query=refined_query, year=None)

    if (not results or len(results) == 0) and refined_type == "tv":
        # 第三梯队：截断片名 + 无年份（原二次搜索逻辑，年份已在第二梯队移除）
        if " " in refined_query:
            fallback_query = refined_query.split(" ")[0]
            logger.info(f"[TMDB] 剧集匹配失败（第二梯队），第三梯队：截断片名搜索: '{fallback_query}'")
            results = scraper.search_tv(query=fallback_query, year=None)

    if not results or len(results) == 0:
        logger.warning(f"[TMDB] 匹配失败: 未找到匹配结果 - {refined_query}")
        db.update_task_status(task_id=task_id, status="failed")
        return None

    # 2. 搜索结果处理与精确匹配
    best_match = results[0]
    query_lower = refined_query.lower().strip()
    query_base = re.sub(r'[\s\-]+\d+$', '', query_lower).strip()
    # 3. 遍历候选结果，寻找精确匹配或宽松匹配
    for candidate in results:
        orig = (candidate.get("original_title") or candidate.get("original_name") or "").lower().strip()
        name = (candidate.get("title") or candidate.get("name") or "").lower().strip()
        if orig == query_lower or name == query_lower:
            best_match = candidate
            logger.info(f"[TMDB] 精确匹配: '{candidate.get('title') or candidate.get('name')}'")
            break
        if query_base and (orig == query_base or name == query_base):
            best_match = candidate
            logger.info(f"[TMDB] 宽松匹配(去集号): '{candidate.get('title') or candidate.get('name')}'")
            break

    # 4. 提取 TMDB ID 和标题
    tmdb_id = best_match.get("id")
    # 根据 rename_lang 决定使用本地化标题还是原始英文标题
    if rename_lang == "en":
        title = (
            best_match.get("original_title")
            or best_match.get("original_name")
            or best_match.get("title")
            or best_match.get("name")
        )
        logger.info(f"[CONFIG] rename_lang=en，使用英文标题: {title}")
    else:
        title = best_match.get("title") or best_match.get("name")
        logger.info(f"[CONFIG] rename_lang=zh，使用中文标题: {title}")
    release_date = best_match.get("release_date") or best_match.get("first_air_date", "")
    year = release_date.split("-")[0] if release_date else None
    logger.info(f"[TMDB] 命中: '{title}' | TMDB_ID={tmdb_id} | 年份={year or 'N/A'} | 类型={refined_type}")

    # 获取 IMDB ID
    imdb_id = ""
    try:
        ext_ids = scraper.get_external_ids(str(tmdb_id), refined_type)
        imdb_id = ext_ids.get("imdb_id", "") or ""
        if imdb_id:
            logger.info(f"[TMDB] IMDb ID 获取成功: {imdb_id}")
        else:
            logger.warning(f"[TMDB] IMDb ID 为空: tmdb_id={tmdb_id}")
    except Exception as e:
        logger.warning(f"[TMDB] 获取 IMDb ID 失败: {e}")
        imdb_id = ""
    logger.info(f"[TMDB] 匹配完成: '{title}' | TMDB={tmdb_id} | IMDB={imdb_id or 'N/A'}")

    # ==========================================
    # 🛡️ IMDb ID 金标准去噪熔断机制（支持剧集分集防重）
    # ==========================================
    # ── 业务链路 ──
    # 1. 检查 IMDb ID 是否已在库中 -> 2. 若存在则标记为 ignored ->
    # 3. 继承同源海报路径 -> 4. 跳过物理归档
    #
    # 设计目标：防止同一媒体被重复入库
    #
    # 拦截策略：
    # - 检测到重复时，标记为 ignored 状态
    # - 更新标题和年份（防止前端显示乱码）
    # - 不执行物理归档，不下载海报
    # ==========================================
    season_num = task.get("season")
    episode_num = task.get("episode")
    if imdb_id and db.check_media_exists(imdb_id, refined_type, season_num, episode_num):
        logger.info(
            f"[SKIP] 检测到重复媒体 (IMDb: {imdb_id}, "
            f"S{season_num}E{episode_num}) 已在库中，跳过重复归档。"
        )
        # 兜底：更新干净标题，防止前端显示丑陋的原始乱码
        db.update_task_title_year(task_id, title, year)
        # 🚨 架构师警告 (DO NOT MODIFY): 核安全边界，改动极易引发死锁或路径穿越。
        # 当文件被判定为“物理重复”时，绝对不允许直接 return 或仅调用 `update_task_status`。
        # 必须调用 `mark_task_as_ignored_and_inherit`，该调用具有“原子语义”：
        #   1) 跨表查找同源已归档任务的 `local_poster_path`
        #   2) 将 `ignored` 状态 + `local_poster_path` 一次性写回 DB
        # 若拆分/内联/省略此调用，前端将出现破图（ignored 的 VHS 故障层失去本地海报锚点 → 白板空图）。
        db.mark_task_as_ignored_and_inherit(
            task_id=task_id,
            imdb_id=imdb_id,
            media_type=refined_type,
            season=season_num,
            episode=episode_num,
            tmdb_id=int(tmdb_id) if tmdb_id else None,
        )
        # 🚨 架构师警告结束（保持原子调用，不要拆分） 
        return None

    return {
        "tmdb_id": tmdb_id,
        "title": title,
        "year": year,
        "imdb_id": imdb_id,
        "season_num": season_num,
        "episode_num": episode_num,
    }


def _step_archive_and_metadata(
    db,
    task: dict,
    task_id,
    file_path: str,
    tmdb_api_key: str,
    poster_lang: str,
    refined_type: str,
    tmdb_data: dict,
) -> str | None:
    """
    原子步骤 4: 就地补录 / 归档全链路 + NFO/海报写入

    业务链路：1. 检查文件是否来自 library 路径或已归档 -> 2. 若是则进入就地补录模式 ->
    3. 计算元数据目录（剧集需上升一级）-> 4. 写入 NFO 和海报 ->
    5. 更新 DB 元数据（不移动文件）

    Returns:
        target_path — 最终归档路径
        None        — 归档失败或路径已被占用（ignored），主流程应 return False, True
    """
    tmdb_id     = tmdb_data["tmdb_id"]
    title       = tmdb_data["title"]
    year        = tmdb_data["year"]
    imdb_id     = tmdb_data["imdb_id"]
    season_num  = tmdb_data["season_num"]
    episode_num = tmdb_data["episode_num"]

    task_status      = task.get("status", "")
    task_file_path   = task.get("path", "")
    _is_library_file = False

    # ==========================================
    # 🏥 就地补录检测（In-Place Metadata Injection）
    # ==========================================
    # ── 业务链路 ──
    # 1. 检查文件是否来自 library 路径或已归档 -> 2. 若是则进入就地补录模式 ->
    # 3. 计算元数据目录（剧集需上升一级）-> 4. 写入 NFO 和海报 ->
    # 5. 更新 DB 元数据（不移动文件）
    #
    # 就地补录 vs 归档全链路：
    # - 就地补录：文件已在媒体库，仅写入 NFO 和海报，不移动文件
    # - 归档全链路：文件在下载目录，需要移动到媒体库并写入元数据
    # ==========================================

    # ── Step 1: 检查文件是否来自 library 路径 ──
    # 业务链路：1. 读取所有配置的 library 路径 -> 2. 规范化路径格式 ->
    # 3. 检查文件是否在 library 路径下
    all_cfg = db.get_all_config()
    _lib_paths = [
        os.path.normpath(p.get("path", "")).lower()
        for p in all_cfg.get("paths", [])
        if p.get("type") == "library" and p.get("enabled", False) and p.get("path")
    ]
    _file_norm = os.path.normpath(task_file_path).lower()
    if task_status == "archived" or any(_file_norm.startswith(lp) for lp in _lib_paths):
        _is_library_file = True

    target_path       = None
    local_poster_path = None
    metadata_dir      = None
    target_dir        = None

    # ── Step 2: 就地补录模式处理 ──
    # 业务链路：1. 若文件来自 library 则进入就地补录模式 -> 2. 计算元数据目录 ->
    # 3. 若为剧集则上升一级到剧集根目录 -> 4. 设置 target_path 为当前路径
    if _is_library_file:
        logger.info(f"[ORG] 就地补录模式：文件来自 library 路径或已归档，仅更新元数据")
        metadata_dir = os.path.dirname(task_file_path)
        # 🚀 剧集目录层级修正：必须将 NFO 和海报写在剧集根目录，而不是 Season 文件夹里
        import re as _re_meta
        if _re_meta.match(r'^(Season|S)\s*\d+$|^Specials$', os.path.basename(metadata_dir), _re_meta.IGNORECASE):
            metadata_dir = os.path.dirname(metadata_dir)
        target_path = task_file_path
    else:
        # ── 归档全链路（Archive Full Pipeline）──
        # 业务链路：1. 获取媒体库根路径 -> 2. 构建目标目录结构 ->
        # 3. 生成目标文件名 -> 4. 计算元数据目录 -> 5. 移动文件到媒体库
        #
        # 电影目录结构：/media/movies/The Matrix (1999)/The Matrix (1999).mkv
        # 剧集目录结构：/media/tv/Breaking Bad (2008)/Season 1/Breaking Bad (2008) - S01E01.mkv
        # 元数据位置：电影 movie.nfo + poster.jpg；剧集 tvshow.nfo + poster.jpg
        library_root = db.get_active_library_path(refined_type)
        logger.info(f"[ORG] 媒体库根路径: {library_root}")
        file_ext = os.path.splitext(file_path)[1]
        from app.services.scraper.cleaner import MediaCleaner as _MCOrg
        safe_title = _MCOrg.sanitize_filename(title)
        logger.info(f"[ORG] 标题净化: '{title}' -> '{safe_title}'")
        season_num = season_num or 1

        # ── Step 1: 电影归档 ──
        # 业务链路：1. 构建文件夹名（标题 + 年份）-> 2. 生成目标文件名 ->
        # 3. 计算元数据目录（与文件夹相同）
        if refined_type == "movie":
            folder_name     = f"{safe_title} ({year})" if year else safe_title
            target_dir      = os.path.join(library_root, folder_name)
            target_filename = f"{folder_name}{file_ext}"
            target_path     = os.path.join(target_dir, target_filename)
            metadata_dir    = target_dir
        else:
            # ── Step 2: 剧集归档 ──
            # 业务链路：1. 构建剧集根目录（标题 + 年份）-> 2. 从路径补充季号 ->
            # 3. 构建 Season 子目录 -> 4. 生成目标文件名（S##E##格式）->
            # 5. 计算元数据目录（剧集根目录）
            folder_name = f"{safe_title} ({year})" if year else safe_title
            episode_num = episode_num or 1
            if season_num == 1 and file_path:
                for _part in Path(file_path).parts:
                    _m = re.search(r'(?:Season|S)\s*(\d{1,2})\b', _part, re.IGNORECASE)
                    if _m:
                        _path_season = int(_m.group(1))
                        if _path_season != 1:
                            season_num = _path_season
                            logger.info(f"[ORG] 从路径补充季号: {file_path} -> season={season_num}")
                        break
            season_folder   = f"Season {int(season_num)}"
            show_root_dir   = os.path.join(library_root, folder_name)
            target_dir      = os.path.join(show_root_dir, season_folder)
            metadata_dir    = show_root_dir
            target_filename = f"{folder_name} - S{season_num:02d}E{episode_num:02d}{file_ext}"
            target_path     = os.path.join(target_dir, target_filename)

        # 物理路径安全检查（路径防穿越校验）
        try:
            _resolved_target = Path(target_path).resolve()
            _resolved_lib    = Path(library_root).resolve()
            _resolved_target.relative_to(_resolved_lib)
        except ValueError:
            logger.error(f"[SECURITY] 路径穿越拦截: {target_path}")
            db.update_task_status(task_id=task_id, status="failed")
            return None

    logger.info(f"[ORG] 目标路径: {target_path}")

    # 2. 统一执行防重拦截并提取海报
    if db.check_task_exists_by_path(target_path):
        logger.info(f"[SKIP] 目标路径已被存量库占用，拦截重复翻译入库 -> {target_path}")
        local_poster_path = None
        for poster_name in ["poster.jpg", "poster.png"]:
            candidate = os.path.join(metadata_dir, poster_name)
            if os.path.exists(candidate):
                local_poster_path = candidate
                logger.info(f"[SKIP] 复用存量库海报: {local_poster_path}")
                break
        db.update_task_title_year(task_id, title, year)
        _is_arc = task.get("is_archive", False)
        if _is_arc:
            db.update_any_task_metadata(
                task_id=task_id, is_archive=True,
                imdb_id=imdb_id,
                tmdb_id=str(tmdb_id) if tmdb_id else None,
                title=title, year=year,
                target_path=target_path,
                local_poster_path=local_poster_path,
                sub_status="success",
            )
        else:
            # 热表任务：确保 continue/return 前持久化终态，避免 pending 泄漏
            try:
                db.update_task_is_active(task_id, 1)
            except Exception:
                pass
        db.update_task_status(
            task_id=task_id, status="ignored",
            tmdb_id=int(tmdb_id) if tmdb_id else None,
            imdb_id=imdb_id, target_path=target_path,
            local_poster_path=local_poster_path,
            sub_status="success",
        )
        return None

    # 3. 如果没被拦截，执行物理操作和元数据写入
    if _is_library_file:
        # 就地补录：不移动文件，仅写入元数据
        try:
            meta_manager = MetadataManager(tmdb_api_key, language="zh-CN" if poster_lang == "zh" else "en-US")
            nfo_filename = "movie.nfo" if refined_type == "movie" else "tvshow.nfo"
            nfo_path = os.path.join(metadata_dir, nfo_filename)
            try:
                nfo_ok = meta_manager.generate_nfo(
                    tmdb_id=str(tmdb_id), media_type=refined_type,
                    output_path=nfo_path, title=title, year=year
                )
                if nfo_ok:
                    logger.info(f"[STORAGE] 就地补录 NFO 写入成功: {nfo_path}")
            except Exception as nfo_err:
                logger.warning(f"[STORAGE] 就地补录 NFO 生成异常，已跳过: {nfo_err}")
            try:
                local_poster_path = meta_manager.download_poster(
                    tmdb_id=str(tmdb_id), media_type=refined_type,
                    output_dir=metadata_dir, title=title
                )
                if local_poster_path:
                    logger.info(f"[STORAGE] 就地补录海报写入成功: {local_poster_path}")
            except Exception as poster_err:
                logger.warning(f"[STORAGE] 就地补录海报下载异常，已跳过: {poster_err}")
            try:
                meta_manager.download_fanart(
                    tmdb_id=str(tmdb_id), media_type=refined_type,
                    output_dir=metadata_dir, title=title
                )
            except Exception as fanart_err:
                logger.warning(f"[STORAGE] 就地补录 Fanart 下载异常，已跳过: {fanart_err}")
        except Exception as inplace_err:
            logger.error(f"[ORG] 就地补录流程异常: {inplace_err}", exc_info=True)

        # 🚀 存量文件轻量级更新：如果是 archived 任务补充 imdb_id，不执行物理搬运
        if task.get("status") == "archived":
            logger.info(f"[ORG] 存量库文件已补齐 IMDb ID: {imdb_id}，更新元数据即可")
            _is_arc = task.get("is_archive", False)
            db.update_any_task_metadata(
                task_id, _is_arc,
                imdb_id=imdb_id if imdb_id else None,
                tmdb_id=str(tmdb_id) if tmdb_id else None,
                sub_status="pending", title=title, year=year
            )
            return target_path
    else:
        # ==========================================
        # 🚀 归档全链路（Full Archive Pipeline）
        # ==========================================
        # 设计目标：将下载目录中的文件归档到媒体库，并补充元数据
        #
        # 完整流程：1. 创建目标目录 -> 2. SmartLink（硬链接>软链接>复制）->
        # 3. 生成 NFO -> 4. 下载海报 -> 5. 下载 Fanart -> 6. 更新数据库
        # ==========================================
        try:
            logger.info(f"[ORG] 源文件路径: {file_path}")
            os.makedirs(target_dir, exist_ok=True)
            success, link_type = SmartLink.create_link(file_path, target_path)
            if success:
                logger.info(f"[ORG] 归档成功 ({link_type}): {target_path}")
                if link_type == "already_exists":
                    logger.info(f"[ORG] 文件已存在，跳过元数据重复下载，直接复用: {target_path}")
                    for poster_name in ["poster.jpg", "poster.png"]:
                        candidate = os.path.join(metadata_dir, poster_name)
                        if os.path.exists(candidate):
                            local_poster_path = candidate
                            break
                else:
                    meta_manager = MetadataManager(tmdb_api_key, language="zh-CN" if poster_lang == "zh" else "en-US")
                    nfo_filename = "movie.nfo" if refined_type == "movie" else "tvshow.nfo"
                    nfo_path = os.path.join(metadata_dir, nfo_filename)
                    try:
                        nfo_ok = meta_manager.generate_nfo(
                            tmdb_id=str(tmdb_id), media_type=refined_type,
                            output_path=nfo_path, title=title, year=year
                        )
                        if nfo_ok:
                            logger.info(f"[STORAGE] NFO 写入成功: {nfo_path}")
                        else:
                            logger.warning(f"[STORAGE] NFO 写入失败，已跳过: {nfo_path}")
                    except Exception as nfo_err:
                        logger.warning(f"[STORAGE] NFO 生成异常，已跳过: {nfo_err}")
                    try:
                        local_poster_path = meta_manager.download_poster(
                            tmdb_id=str(tmdb_id), media_type=refined_type,
                            output_dir=metadata_dir, title=title
                        )
                        if local_poster_path:
                            logger.info(f"[STORAGE] 海报写入成功: {local_poster_path}")
                        else:
                            logger.warning(f"[STORAGE] 海报下载失败，DB 写入不受影响")
                    except Exception as poster_err:
                        logger.warning(f"[STORAGE] 海报下载异常，已跳过: {poster_err}")
                    try:
                        fanart_path = meta_manager.download_fanart(
                            tmdb_id=str(tmdb_id), media_type=refined_type,
                            output_dir=metadata_dir, title=title
                        )
                        if fanart_path:
                            logger.info(f"[STORAGE] Fanart 写入成功: {fanart_path}")
                    except Exception as fanart_err:
                        logger.warning(f"[STORAGE] Fanart 下载异常，已跳过: {fanart_err}")
            else:
                logger.error(f"[ORG] 归档失败: {link_type}")
                target_path = None
                local_poster_path = None
        except Exception as org_error:
            logger.error(f"[ORG] [FAIL] 归档流程异常: {org_error}", exc_info=True)
            target_path = None
            local_poster_path = None
    # ── 就地补录/归档全链路 结束 ──

    db.update_task_title_year(
        task_id=task_id, title=title, year=year,
        season=season_num if refined_type == "tv" else None
    )
    db.update_task_status(
        task_id=task_id, status="archived",
        tmdb_id=int(tmdb_id), 

        imdb_id=imdb_id if imdb_id else "",
        target_path=target_path,
        local_poster_path=local_poster_path,
        task_type=refined_type
    )
    logger.info(f"[TMDB] 已校准任务 {task_id} 的媒体类型为: {refined_type}")
    return target_path


def _process_single_task(
    db,
    scraper,
    ai_agent,
    rename_lang: str,
    poster_lang: str,
    tmdb_api_key: str,
    task: dict,
) -> tuple:
    """
    流水线编排器 (Orchestrator)

    ── 业务链路总览 ──
    NFO 短路拦截 -> 存量字幕省流 -> AI 提炼 -> TMDB 搜索 ->
    IMDb 防重熔断 -> 就地补录 / 归档全链路 -> 字幕白嫖

    Returns:
        (is_success, is_failed): 布尔值元组，供主循环累加统计
    """
    try:
        clean_name = task.get("clean_name", "")
        file_name  = task.get("file_name", "")
        file_path  = task.get("path", "")
        task_id    = task.get("id")
        media_type = task.get("type", "movie")
        logger.info(f"[TMDB] 正在处理: {clean_name or file_name} (ID: {task_id})")

        # 1. NFO 短路拦截
        if _step_nfo_shortcut(db, task, file_path, task_id, clean_name):
            return True, False

        # 2. 极致省流：存量库为补 ID 进来的任务，先看有没有字幕
        # 业务链路：1. 检查任务是否已归档且缺 imdb_id -> 2. 检查本地是否有字幕 ->
        # 3. 若有字幕则跳过 IMDb ID 补充刮削（节省 Token）
        if task.get("status") == "archived" and not task.get("imdb_id"):
            _sub_path = task.get("target_path") or file_path
            if _sub_path and _check_local_subtitles(_sub_path, sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))):
                logger.info(f"[SCRAPE] 存量库本地已有字幕，跳过 IMDb ID 补充刮削，节省 Token -> {_sub_path}")
                db.update_any_task_metadata(task_id, task.get("is_archive", False), sub_status="success")
                return True, False

        # 3. AI 提炼
        refined_query, refined_year, refined_type = _step_ai_extraction(
            db, ai_agent, task, task_id, file_name, file_path, clean_name, media_type
        )

        # 4. TMDB 搜索与防重拦截
        tmdb_data = _step_tmdb_search_and_dup_check(
            db, scraper, task, task_id,
            refined_query, refined_year, refined_type, rename_lang
        )
        if not tmdb_data:
            return False, True

        # 5. 物理归档 + 元数据写入
        target_path = _step_archive_and_metadata(
            db, task, task_id, file_path,
            tmdb_api_key, poster_lang, refined_type, tmdb_data
        )
        # 就地补录的存量 archived 任务 target_path 有值但已轻量更新，直接成功
        # 归档失败（路径穿越或 SmartLink 失败）target_path=None 且 DB 已写 failed
        if target_path is None and not task.get("status") == "archived":
            return False, True

        # 6. 字幕白嫖（Local Subtitle Detection）
        # ── 业务链路 ──
        # 1. 获取字幕检测路径（优先使用 target_path）-> 2. 调用本地字幕检测函数 ->
        # 3. 若发现本地字幕则标记为 success -> 4. 否则标记为 pending（等待搜索）
        #
        # 优势：零 API 消耗，归档后立即显示字幕状态，支持手动字幕
        _sub_check_path = target_path or file_path
        if _sub_check_path and _check_local_subtitles(
            _sub_check_path,
            sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))
        ):
            # ── Step 1: 发现本地字幕 ──
            # 业务链路：1. 记录日志 -> 2. 更新 sub_status 为 success -> 3. 跳过后续字幕搜索
            logger.info(f"[SUBTITLE] [白嫖] 发现本地字幕，直接标记 success -> {_sub_check_path}")
            db.update_task_sub_status(task_id, "success")
        else:
            # ── Step 2: 未发现本地字幕 ──
            # 业务链路：1. 更新 sub_status 为 pending -> 2. 等待后续字幕搜索任务处理
            db.update_task_sub_status(task_id, "pending")

        return True, False

    except Exception as e:
        logger.error(f"[TMDB] 匹配失败: {str(e)}")
        try:
            db.update_task_status(task_id=task.get("id"), status="failed")
        except Exception:
            pass
        return False, True

    time.sleep(0.3)
    return False, False  # 保底返回


# ==========================================
# 路由端点
# ==========================================

@router.post("/scrape_all", response_model=ScanResponse)
async def trigger_scrape_all(background_tasks: BackgroundTasks):
    """
    触发全量刮削任务（后台线程执行，快速返回）。

    业务链路：
    触发刮削 → 后台线程遍历待刮削任务 → TMDB 三梯队降级搜索 + IMDb 金标准防重 → 生成 NFO/海报/字幕状态 → 更新仪表盘计数缓存。

    Args:
        background_tasks: FastAPI 后台任务容器，用于投递 `perform_scrape_all_task_sync`（避免阻塞请求线程）。

    Returns:
        ScanResponse: 立即返回“已启动/运行中”的确认消息；真实进度通过 `GET /scrape_all/status` 轮询。

    Raises:
        HTTPException:
            - 500: 后台任务投递失败或运行时异常。
    """
    global scrape_all_status

    if scrape_all_status["is_running"]:
        logger.warning("[API] 全量刮削任务已在运行中")
        return ScanResponse(message="全量刮削任务已在运行中，请稍后再试")

    try:
        async def run_scrape_in_thread():
            try:
                await asyncio.to_thread(perform_scrape_all_task_sync)
            except BaseException as e:
                logger.error(f"[SCRAPE] 后台线程异常: {e}", exc_info=True)
                scrape_all_status["is_running"] = False
                scrape_all_status["error"] = f"严重中断: {str(e)}"
                raise

        background_tasks.add_task(run_scrape_in_thread)
        logger.info("[API] 全量刮削任务已加入后台线程队列")
        return ScanResponse(message="全量刮削任务已启动，正在后台线程执行")
    except Exception as e:
        logger.error(f"[API] 启动全量刮削失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动全量刮削失败: {str(e)}")


@router.get("/scrape_all/status")
async def get_scrape_all_status() -> Dict[str, Any]:
    """
    获取全量刮削任务状态（用于前端轮询渲染运行态）。

    业务链路：
    只读返回内存态 `scrape_all_status`，用于 UI 展示与按钮态控制；不触发 TMDB/磁盘 I/O。

    Returns:
        Dict[str, Any]:
            - is_running: 是否正在运行
            - last_run_time: 上次运行时间（Unix 时间戳）
            - processed_count: 已处理的任务数量
            - error: 错误信息（若有）
    """
    return {
        "is_running": scrape_all_status["is_running"],
        "last_run_time": scrape_all_status["last_run_time"],
        "processed_count": scrape_all_status["processed_count"],
        "error": scrape_all_status["error"]
    }


# ==========================================
# 精准补录 - 数据模型
# ==========================================

class ManualRebuildRequest(BaseModel):
    """手动补录请求体"""
    task_id: int
    is_archive: bool = True
    tmdb_id: Optional[int] = None
    keyword_hint: Optional[str] = None
    media_type: str = "movie"
    refix_nfo: bool = True
    refix_poster: bool = True
    refix_subtitle: bool = True
    nuclear_reset: bool = False   # 核级重置：清理目录 + 重命名视频文件 + 同步 target_path
    season: Optional[int] = None   # 用户强制指定季数（覆盖 DB 值）
    episode: Optional[int] = None  # 用户强制指定集数（覆盖 DB 值）


def _safe_delete_metadata_files(metadata_dir: str, library_root: str) -> dict:
    """
    安全删除 metadata_dir 下的旧元数据文件（双重路径防穿越校验）。
    只删白名单：poster.*, fanart.*, *.ai.*
    """
    resolved_meta = Path(metadata_dir).resolve()
    resolved_lib  = Path(library_root).resolve()
    try:
        resolved_meta.relative_to(resolved_lib)
    except ValueError:
        raise PermissionError(
            f"[SECURITY] metadata_dir '{metadata_dir}' 不在 library_root '{library_root}' 内"
        )
    deleted: dict = {"poster": [], "fanart": [], "ai_subtitles": []}
    for pattern, category in [("poster.*", "poster"), ("fanart.*", "fanart")]:
        for f in resolved_meta.glob(pattern):
            try:
                f.resolve().relative_to(resolved_meta)
            except ValueError:
                continue
            if f.is_file():
                f.unlink()
                deleted[category].append(str(f))
                logger.info(f"[CLEANUP] 已删除: {f}")
    for f in resolved_meta.iterdir():
        if not f.is_file():
            continue
        try:
            f.resolve().relative_to(resolved_meta)
        except ValueError:
            continue
        if re.search(r'\.ai\.', f.name, re.IGNORECASE):
            f.unlink()
            deleted["ai_subtitles"].append(str(f))
            logger.info(f"[CLEANUP] 已删除残留 AI 字幕: {f}")
    return deleted


# 视频本体扩展名白名单（核级清理时保留）— 静态兜底，动态值由调用方从 DB 读取后传入
_VIDEO_EXTENSIONS_FALLBACK = frozenset({'.mkv', '.mp4', '.avi', '.ts', '.m2ts', '.mov', '.wmv', '.flv', '.rmvb', '.webm', '.iso', '.vob', '.mpg', '.mpeg', '.m4v'})


def _parse_video_exts(raw: str) -> frozenset:
    """将逗号分隔的后缀字符串解析为小写 frozenset。"""
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts) if parts else _VIDEO_EXTENSIONS_FALLBACK


def _parse_sub_exts(raw: str) -> frozenset:
    """将逗号分隔的字幕后缀字符串解析为小写 frozenset。"""
    _fallback = frozenset({'.srt', '.ass', '.vtt', '.sub', '.idx'})
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts) if parts else _fallback


def _nuclear_clean_directory(metadata_dir: str, library_root: str, video_exts: frozenset = None, protect_metadata: bool = False) -> dict:
    """
    核级清理：删除 metadata_dir 下除视频本体以外的所有文件。

    安全保险栓：
    1. metadata_dir 必须是 library_root 的子路径（防越权）
    2. library_root 不得为根目录或常见危险路径（防止误删 /storage 根目录）
    3. 每个文件二次校验在 metadata_dir 内（防软链穿越）
    4. 只操作 metadata_dir 本层文件，不递归子目录
    5. video_exts 白名单内的文件绝对保留
    """
    _video_exts = video_exts if video_exts else _VIDEO_EXTENSIONS_FALLBACK

    resolved_meta = Path(metadata_dir).resolve()
    resolved_lib  = Path(library_root).resolve()

    # 保险栓 1：library_root 不得为危险路径（深度 < 2 的路径视为危险）
    if len(resolved_lib.parts) < 3:
        raise PermissionError(f"[NUCLEAR SAFELOCK] library_root 路径过浅，拒绝操作: {library_root}")

    # 保险栓 2：metadata_dir 必须是 library_root 的子路径
    try:
        resolved_meta.relative_to(resolved_lib)
    except ValueError:
        raise PermissionError(f"[NUCLEAR SAFELOCK] metadata_dir '{metadata_dir}' 不在 library_root '{library_root}' 内，拒绝清理")

    deleted, kept_videos = [], []
    _protected_names = {"tvshow.nfo", "movie.nfo", "poster.jpg", "poster.png", "poster.webp", "fanart.jpg", "fanart.png", "fanart.webp"}
    for f in resolved_meta.iterdir():
        if not f.is_file():
            continue  # 跳过子目录
        # 保险栓 3：防软链穿越
        try:
            f.resolve().relative_to(resolved_meta)
        except ValueError:
            logger.warning(f"[NUCLEAR SAFELOCK] 跳过越界文件: {f}")
            continue
        if f.suffix.lower() in _video_exts:
            kept_videos.append(str(f))
            logger.info(f"[NUCLEAR] 保留视频本体: {f.name}")
        elif protect_metadata and f.name.lower() in _protected_names:
            logger.info(f"[NUCLEAR] 金标准护盾生效，保留元数据: {f.name}")
            continue
        else:
            f.unlink()
            deleted.append(str(f))
            logger.info(f"[NUCLEAR] 已删除: {f.name}")

    logger.info(f"[NUCLEAR] 清理完成: 删除 {len(deleted)} 个文件，保留视频 {len(kept_videos)} 个")
    return {"deleted": deleted, "kept_videos": kept_videos}


def _rename_video_file(
    video_path: str, title: str, year: str,
    media_type: str, season: Optional[int] = None, episode: Optional[int] = None
) -> str:
    """
    按 TMDB 元数据重命名视频文件。
    电影：标题 (年份).ext
    剧集：标题 (年份) - SxxExx.ext
    返回新路径（若未重命名则返回原路径）。
    """
    safe_title = re.sub(r'[\\/:*?"|<>]', '_', title.strip())
    year_str = f" ({year})" if year else ""
    if media_type == 'tv' and season is not None and episode is not None:
        ep_str = f" - S{str(season).zfill(2)}E{str(episode).zfill(2)}"
    else:
        ep_str = ""
    ext = Path(video_path).suffix
    new_name = f"{safe_title}{year_str}{ep_str}{ext}"
    new_path = str(Path(video_path).parent / new_name)

    if video_path == new_path:
        return video_path

    # 防冲突：若目标文件已存在且不是自身，追加序号
    counter = 1
    candidate = new_path
    while Path(candidate).exists() and candidate != video_path:
        stem = f"{safe_title}{year_str}{ep_str}_{counter}"
        candidate = str(Path(video_path).parent / f"{stem}{ext}")
        counter += 1
    new_path = candidate

    os.rename(video_path, new_path)
    logger.info(f"[RENAME] '{Path(video_path).name}' → '{Path(new_path).name}'")
    return new_path


@router.get("/search_tmdb")
async def search_tmdb(
    keyword: str,
    media_type: str = "movie",
) -> list:
    """
    TMDB 关键词搜索（用于手动补录的候选选择，返回 Top N）。

    业务链路：
    校验 TMDB API Key → 调用 `TMDBAdapter.search_media` → 对前 10 条做轻量映射 →
    仅为前 5 条补充 IMDb ID（批量节流，避免 N 次外部请求拖慢响应）→ 返回候选列表。

    Args:
        keyword: 搜索关键词（Query 参数）。
        media_type: 媒体类型（Query 参数，movie/tv）。

    Returns:
        list[dict]: 候选列表（最多 10 条），字段包含 tmdb_id/title/year/overview/poster_path/imdb_id。

    Raises:
        HTTPException:
            - 500: 未配置 TMDB API Key。
            - 502: TMDB 请求失败（上游不可用/响应异常）。
    """
    from app.infra.database import get_db_manager as _get_db
    db = _get_db()
    tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
    if not tmdb_api_key:
        raise HTTPException(status_code=500, detail="未配置 TMDB API Key")
    from app.services.metadata.adapters import TMDBAdapter
    scraper = TMDBAdapter(api_key=tmdb_api_key)
    try:
        results = scraper.search_media(keyword.strip(), media_type)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TMDB 搜索失败: {e}")
    # 为前 5 条结果批量获取真实 IMDb ID（避免全量 N 次请求拖慢响应）
    enriched = []
    for r in results[:10]:
        tmdb_result_id = str(r.get("id") or "")
        imdb_id: Optional[str] = None
        if tmdb_result_id and len(enriched) < 5:
            try:
                ext = scraper.get_external_ids(tmdb_result_id, media_type)
                imdb_id = ext.get("imdb_id") or None
            except Exception:
                pass
        enriched.append({
            "tmdb_id":     r.get("id"),
            "title":       r.get("title") or r.get("name") or "",
            "year":        (r.get("release_date") or r.get("first_air_date") or "")[:4],
            "overview":    (r.get("overview") or "")[:200],
            "poster_path": r.get("poster_path"),
            "imdb_id":     imdb_id,
        })
    return enriched


@router.post("/manual_rebuild")
async def manual_rebuild(
    body: ManualRebuildRequest,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    精准补录（manual_rebuild）：按需重建 NFO/海报/字幕，并可选核级清理。

    业务链路：
    读取任务记录（热表/冷表）→ 校验 target_path 与 library_root 安全边界 → **IMDb 金标准物理防爆护盾**预检 →
    （可选）核级清理/视频重命名/目录土木工程 → DB 同步（含 TV 季/集号作用域护盾）→ 按开关补录 NFO/海报/字幕 →
    返回补录结果与提示信息。

    Body:
        body: ManualRebuildRequest，关键字段：
            - task_id: 目标任务 ID
            - is_archive: 是否来自归档表（冷表）
            - media_type: movie/tv
            - refix_nfo/refix_poster/refix_subtitle: 三路补录开关
            - tmdb_id/keyword_hint: 元数据定位（优先 tmdb_id）
            - nuclear_reset: 是否执行核级清理
            - season/episode: TV 季/集号（用户强制指定优先，DB 值兜底）
        background_tasks: FastAPI 后台任务容器（用于线程化执行重操作，避免阻塞）。

    Returns:
        Dict[str, Any]: 补录结果摘要（nfo/poster/subtitle/nuclear 等状态字段）与可读 message。

    Raises:
        HTTPException:
            - 400: 请求体缺少必要字段或任务缺少 target_path 等前置条件。
            - 404: task_id 对应任务不存在（热表/冷表均未命中）。
            - 500: 未配置 TMDB API Key 或内部运行时异常。
    """
    from app.infra.database import get_db_manager as _get_db
    db = _get_db()

    # ── Step 1: 读取任务记录 ──
    # 1. 根据 is_archive 标志选择热表或冷表 -> 2. 查询任务记录 -> 3. 校验任务存在性
    if body.is_archive:
        records = db.get_archived_data()
    else:
        records = db.get_all_data(include_ignored=True)
    task_record = next((r for r in records if r["id"] == body.task_id), None)
    if not task_record:
        raise HTTPException(
            status_code=404,
            detail=f"任务不存在（task_id={body.task_id}, is_archive={body.is_archive}）"
        )

    # ── Step 2: 校验 target_path 有效性 ──
    # 1. 优先使用 target_path（已重命名的目标路径）-> 2. 降级到 path（原始路径）-> 3. 提取元数据目录
    target_path: str = task_record.get("target_path") or task_record.get("path") or ""
    if not target_path:
        raise HTTPException(status_code=400, detail="任务缺少 target_path")

    metadata_dir = os.path.dirname(os.path.abspath(target_path))
    # TV 单集：若当前目录是 Season 子目录，则上升一级到剧集根目录（tvshow.nfo 存放位置）
    if re.match(r'^(Season|S)\s*\d+$|^Specials$', os.path.basename(metadata_dir), re.IGNORECASE):
        metadata_dir = os.path.dirname(metadata_dir)

    # ── Step 3: 确定 library_root（安全边界） ──
    # 1. 从配置读取活跃媒体库路径 -> 2. 降级到 metadata_dir（若配置缺失）
    try:
        library_root = db.get_active_library_path(body.media_type)
    except Exception:
        library_root = metadata_dir

    # ── Step 4: 初始化 TMDB 适配器 ──
    # 1. 读取 TMDB API Key -> 2. 读取多语言偏好 -> 3. 创建 TMDBAdapter 和 MetadataManager
    tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
    if not tmdb_api_key:
        raise HTTPException(status_code=500, detail="未配置 TMDB API Key")

    rename_lang = db.get_config("rename_lang", "zh")
    poster_lang = db.get_config("poster_lang", "zh")
    from app.services.metadata.adapters import TMDBAdapter
    from app.services.metadata.metadata_manager import MetadataManager
    scraper = TMDBAdapter(api_key=tmdb_api_key, rename_lang=rename_lang, poster_lang=poster_lang)
    meta_manager = MetadataManager(tmdb_api_key=tmdb_api_key)

    # ── Step 5: 解析 TMDB 元数据 ──
    # 1. 优先使用前端传入的 tmdb_id -> 2. 降级到 DB 中已有的 tmdb_id -> 3. 若无 ID 则尝试关键词搜索
    new_tmdb_id: Optional[int] = body.tmdb_id
    # Fix: fallback 到数据库中已有的 tmdb_id（单点补录海报/字幕时前端不传 tmdb_id）
    if not new_tmdb_id:
        _db_tmdb = task_record.get("tmdb_id")
        if _db_tmdb:
            try:
                new_tmdb_id = int(_db_tmdb)
            except (ValueError, TypeError):
                new_tmdb_id = None
    new_title: str = task_record.get("title") or ""
    new_year: str = str(task_record.get("year") or "")
    new_imdb_id: str = task_record.get("imdb_id") or ""
    # TV 任务季/集号：必须在整个 manual_rebuild 生命周期内可用（非核级模式同样需要写回 DB）
    # 请求值优先（用户强制指定），DB 值兜底
    task_season  = body.season  if body.season  is not None else task_record.get("season")
    task_episode = body.episode if body.episode is not None else task_record.get("episode")

    # ── Step 6: 获取 TMDB 详情或搜索 ──
    # 1. 若有 tmdb_id，直接获取详情 -> 2. 若无 ID 但有关键词，执行搜索 -> 3. 提取标题、年份、IMDb ID
    if new_tmdb_id:
        try:
            detail = scraper.get_tv_details(str(new_tmdb_id)) if body.media_type == "tv" else scraper.get_movie_details(str(new_tmdb_id))
            if detail:
                new_title = detail.get("title") or detail.get("name") or new_title
                release = detail.get("release_date") or detail.get("first_air_date") or ""
                new_year = release[:4] if release else new_year
                new_imdb_id = (detail.get("external_ids") or {}).get("imdb_id") or new_imdb_id
        except Exception as e:
            logger.warning(f"[REBUILD] 获取 TMDB 详情失败: {e}")
    elif body.keyword_hint and body.keyword_hint.strip():
        try:
            results = scraper.search_media(body.keyword_hint.strip(), body.media_type)
            if results:
                hit = results[0]
                new_tmdb_id = int(hit.get("id") or 0) or None
                new_title = hit.get("title") or hit.get("name") or new_title
                release = hit.get("release_date") or hit.get("first_air_date") or ""
                new_year = release[:4] if release else new_year
                if new_tmdb_id:
                    ext = scraper.get_external_ids(str(new_tmdb_id), body.media_type)
                    new_imdb_id = ext.get("imdb_id") or new_imdb_id
        except Exception as e:
            logger.warning(f"[REBUILD] TMDB 搜索失败: {e}")

    rebuilt: Dict[str, Any] = {"nfo": False, "poster": False, "subtitle": "skipped", "nuclear": False}

    # ── 3.4 金标准元数据防重预检 (Pre-emptive IMDb Validation) ────────
    # 业务链路：1. 读取本地 NFO 文件 -> 2. 解析 IMDb ID -> 3. 与新 IMDb ID 比对 -> 
    # 4. 若一致则激活防爆护盾（skip_metadata=True），跳过后续 NFO/海报下载
    # 必须在 _nuclear_clean_directory 之前执行，否则 NFO 已被删除无法读取
    skip_metadata = False
    if new_imdb_id:
        check_dir = metadata_dir
        if body.media_type == "tv" and re.match(
            r'^(Season|S)\s*\d+$|^Specials$',
            os.path.basename(check_dir), re.IGNORECASE
        ):
            check_dir = os.path.dirname(check_dir)
        nfo_filename = "tvshow.nfo" if body.media_type == "tv" else "movie.nfo"
        nfo_path_check = Path(check_dir) / nfo_filename
        has_nfo = nfo_path_check.exists()
        # 物理存在性二次校验：poster.* 任意存在即可视为“补录已完成”
        has_poster = any(
            (Path(check_dir) / name).exists()
            for name in ("poster.jpg", "poster.png", "poster.webp")
        )

        if has_nfo:
            try:
                import xml.etree.ElementTree as ET
                with open(nfo_path_check, 'r', encoding='utf-8') as f:
                    _tree = ET.parse(f)
                    _root = _tree.getroot()
                    _existing_imdb = (_root.findtext("imdbid") or "").strip()
                    if not _existing_imdb:
                        for _uid in _root.findall("uniqueid"):
                            if _uid.get("type") == "imdb":
                                _existing_imdb = (_uid.text or "").strip()
                                break
                    if _existing_imdb and _existing_imdb == new_imdb_id.strip():
                        # “金标准护盾”需要同时满足：ID 匹配 + 物理文件存在（缺啥补啥）
                        shield_ok = True
                        if body.refix_poster and not has_poster:
                            shield_ok = False
                            logger.info(
                                f"[REBUILD] 金标准校验通过但物理海报缺失，解除护盾以触发补录: {check_dir}"
                            )
                        skip_metadata = shield_ok
                        if skip_metadata:
                            logger.info(f"[REBUILD] 金标准校验通过且物理完整，开启防爆护盾: imdb={new_imdb_id}")
            except Exception as _e:
                logger.warning(f"[REBUILD] NFO 解析失败，防爆护盾离线: {_e}")
        else:
            # NFO 物理缺失时：绝不允许用“金标准护盾”短路 refix_nfo
            if body.refix_nfo:
                logger.info(f"[REBUILD] NFO 物理缺失，禁止护盾短路: {nfo_path_check}")

    # ── 3.5 核级重置协议（nuclear_reset=True 且有新 TMDB ID 时执行）────────
    # 业务链路：1. 物理层拦截并发 -> 2. 校验 TMDB ID 金标准 -> 3. 执行 _nuclear_clean_directory 清理非视频文件 -> 
    # 4. 重命名视频本体 -> 5. 原子级同步 DB target_path
    # 执行顺序（严格）：核级清理 → 重命名视频 → 立即同步 DB target_path
    # Bug 1 修复：核级清理后强制覆写三个 refix 标志，确保 NFO/海报/字幕必被重建
    if body.nuclear_reset and new_tmdb_id:
        body.refix_nfo      = True
        body.refix_poster   = True
        body.refix_subtitle = True
        # 从数据库读取视频后缀白名单
        _db_video_exts_raw = db.get_config("supported_video_exts", "")
        _db_video_exts = _parse_video_exts(_db_video_exts_raw)
        # 找出目录内视频本体文件（先扫一层，TV 任务无结果时递归深探 Season 子目录）
        video_files = [f for f in Path(metadata_dir).iterdir()
                       if f.is_file() and f.suffix.lower() in _db_video_exts]
        if not video_files and body.media_type == "tv":
            logger.info("[NUCLEAR] 一级目录未找到视频，启动递归深探（TV Season 子目录）")
            video_files = sorted(
                [f for f in Path(metadata_dir).rglob("*")
                 if f.is_file() and f.suffix.lower() in _db_video_exts]
            )
        if not video_files:
            raise HTTPException(status_code=400, detail="[NUCLEAR] 目录及子目录内均未找到视频本体文件，中止操作")
        old_video_path = str(video_files[0])
        new_video_path = old_video_path  # 预设为原路径（异常回滚用）

        try:
            # Step 1: 核级清理（删除非视频文件）
            # 1. 激活防爆护盾（protect_metadata=skip_metadata）-> 2. 删除所有非视频文件 -> 3. 保留 NFO/海报/字幕
            nuclear_result = _nuclear_clean_directory(metadata_dir, library_root, video_exts=_db_video_exts, protect_metadata=skip_metadata)
            logger.info(f"[NUCLEAR] 清理完成: {nuclear_result}")
            rebuilt["nuclear"] = True

            # Step 2: 视频文件重命名
            new_video_path = _rename_video_file(
                old_video_path, new_title, new_year,
                body.media_type, task_season, task_episode
            )

            # Step 2.5: 文件夹土木工程（TV 根目录改名 + 季搬运 / 电影根目录重命名）
            try:
                if body.media_type == "tv" and new_title:
                    # TV 双轨重构：先改根目录名，再搬 Season 小房间
                    tv_root = Path(metadata_dir)  # 剧集根目录（已在 Step 0 跳升）

                    # ── 轨道 1：根目录重命名 ────────────────────────────────
                    expected_show_name = f"{new_title} ({new_year})" if new_year else new_title
                    if tv_root.name != expected_show_name:
                        new_tv_root = tv_root.parent / expected_show_name
                        if new_tv_root.exists():
                            logger.warning(f"[NUCLEAR] TV 根目录目标已存在，跳过重命名: {new_tv_root}")
                        else:
                            # 计算视频相对于旧根的路径，改根后同步更新绝对路径
                            try:
                                rel_path = Path(new_video_path).relative_to(tv_root)
                            except ValueError:
                                rel_path = Path(Path(new_video_path).name)
                            tv_root.rename(new_tv_root)
                            tv_root = new_tv_root
                            new_video_path = str(tv_root / rel_path)
                            metadata_dir = str(tv_root)
                            logger.info(f"[NUCLEAR] TV 根目录已重命名: {expected_show_name}")

                    # ── 轨道 2：Season 目录搬运 ──────────────────────────────
                    if task_season is not None:
                        target_season_dir = tv_root / f"Season {task_season}"
                        target_season_dir.mkdir(parents=True, exist_ok=True)
                        current_video = Path(new_video_path)
                        if current_video.parent.resolve() != target_season_dir.resolve():
                            dest = target_season_dir / current_video.name
                            if dest.exists():
                                logger.warning(f"[NUCLEAR] 目标路径已存在同名文件，跳过移动: {dest}")
                            else:
                                shutil.move(str(current_video), str(dest))
                                new_video_path = str(dest)
                                logger.info(f"[NUCLEAR] TV 视频已移至 Season {task_season}: {dest}")

                elif body.media_type == "movie" and new_title:
                    # 电影：若片名/年份变更，重命名根目录
                    expected_dir_name = f"{new_title} ({new_year})" if new_year else new_title
                    current_root = Path(new_video_path).parent.resolve()
                    if current_root.name != expected_dir_name:
                        new_root = current_root.parent / expected_dir_name
                        if new_root.exists():
                            logger.warning(f"[NUCLEAR] 目标目录已存在，跳过重命名: {new_root}")
                        else:
                            current_root.rename(new_root)
                            new_video_path = str(new_root / Path(new_video_path).name)
                            metadata_dir = str(new_root)
                            logger.info(f"[NUCLEAR] 电影根目录已重命名: {current_root.name} → {expected_dir_name}")
            except (PermissionError, OSError) as dir_err:
                logger.warning(f"[NUCLEAR] 文件夹土木工程失败（不阻断主流程）: {dir_err}")

            # Step 3: 立即同步 DB target_path（重命名与 DB 原子绑定）
            db.update_any_task_metadata(
                body.task_id, body.is_archive,
                target_path=new_video_path,
            )
            target_path = new_video_path  # 后续步骤使用新路径
            metadata_dir = os.path.dirname(os.path.abspath(new_video_path))
            # TV 任务：核级重置后若视频仍在 Season 子目录，跳升 metadata_dir 到剧集根目录
            # 确保 tvshow.nfo / poster.jpg 写入剧集根目录而非 Season 子文件夹
            if body.media_type == "tv" and re.match(
                r'^(Season|S)\s*\d+$|^Specials$',
                os.path.basename(metadata_dir), re.IGNORECASE
            ):
                metadata_dir = os.path.dirname(metadata_dir)
                logger.info(f"[NUCLEAR] TV 元数据目录锁定至剧集根目录: {metadata_dir}")
            logger.info(f"[NUCLEAR] DB target_path 已同步: {new_video_path}")

        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except Exception as nuclear_err:
            # 重命名成功但 DB 失败时：回滚文件名
            if new_video_path != old_video_path and Path(new_video_path).exists():
                try:
                    os.rename(new_video_path, old_video_path)
                    logger.warning(f"[NUCLEAR] 回滚重命名: {new_video_path} → {old_video_path}")
                except Exception as rb_err:
                    logger.error(f"[NUCLEAR] 回滚失败: {rb_err}")
            raise HTTPException(status_code=500, detail=f"api_error_nuclear_reset_failed: {nuclear_err}")

    # 4. refix_nfo: 深度清理（非核级模式）+ 重写 NFO
    if body.refix_nfo and new_tmdb_id:
        if skip_metadata:
            rebuilt["nfo"] = True
            logger.info("[REBUILD] 金标准护盾：沿用现有 NFO，跳过生成")
        else:
            if not body.nuclear_reset:
                # 非核级模式：只做精准清理（poster/fanart/ai字幕）
                try:
                    deleted = _safe_delete_metadata_files(metadata_dir, library_root)
                    logger.info(f"[REBUILD] 精准清理: {deleted}")
                except PermissionError as e:
                    raise HTTPException(status_code=403, detail=str(e))
            nfo_filename = "tvshow.nfo" if body.media_type == "tv" else "movie.nfo"
            nfo_path = os.path.join(metadata_dir, nfo_filename)
            ok = meta_manager.generate_nfo(str(new_tmdb_id), body.media_type, nfo_path, new_title, new_year)
            rebuilt["nfo"] = ok
            logger.info(f"[REBUILD] NFO {'成功' if ok else '失败'}: {nfo_path}")

    # ── Safelock：单点补录海报/字幕时，必须有 TMDB ID ──────────────────────
    # Bug 2 修复：无 tmdb_id 时给出明确提示，而不是静默返回 ❌
    if (body.refix_poster or body.refix_subtitle) and not new_tmdb_id:
        # 若同时请求了 NFO 且 NFO 已成功，说明刚刚拿到了 tmdb_id，不应拦截
        # 只在纯海报/字幕单点补录且确实无 tmdb_id 时才报错
        if not (body.refix_nfo and rebuilt.get("nfo")):
            raise HTTPException(
                status_code=400,
                detail="api_error_missing_tmdb_id"
            )

    # 5. refix_poster: 强制覆盖海报 + Fanart
    if body.refix_poster and new_tmdb_id:
        if skip_metadata:
            # 护盾激活：扫描已有海报文件，赋给 local_poster 供 DB 更新使用
            local_poster = None
            for _pname in ["poster.jpg", "poster.png", "poster.webp"]:
                _pp = Path(metadata_dir) / _pname
                if _pp.exists():
                    local_poster = str(_pp)
                    break
            rebuilt["poster"] = True
            logger.info(f"[REBUILD] 金标准护盾：沿用现有海报，跳过下载: {local_poster}")
        else:
            for _pname in ["poster.jpg", "poster.png", "poster.webp"]:
                _pp = Path(metadata_dir) / _pname
                if _pp.exists():
                    _pp.unlink()
            local_poster = meta_manager.download_poster(str(new_tmdb_id), body.media_type, metadata_dir, new_title)
            rebuilt["poster"] = bool(local_poster)
            logger.info(f"[REBUILD] 海报 {'成功' if local_poster else '失败'}: {local_poster}")
            # 补全 Fanart（背景图）
            try:
                for _fname in ["fanart.jpg", "fanart.png", "fanart.webp"]:
                    _fp = Path(metadata_dir) / _fname
                    if _fp.exists():
                        _fp.unlink()
                local_fanart = meta_manager.download_fanart(str(new_tmdb_id), body.media_type, metadata_dir, new_title)
                logger.info(f"[REBUILD] Fanart {'成功' if local_fanart else '失败'}: {local_fanart}")
            except Exception as fanart_err:
                logger.warning(f"[REBUILD] Fanart 下载失败（不阻断主流程）: {fanart_err}")
    else:
        local_poster = None

    # 6. 更新数据库元数据（合并为一次调用）
    if new_tmdb_id:
        db.update_any_task_metadata(
            body.task_id, body.is_archive,
            tmdb_id=new_tmdb_id,
            imdb_id=new_imdb_id or None,
            title=new_title or None,
            year=new_year or None,
            local_poster_path=local_poster or None,
            sub_status="pending" if body.refix_subtitle else None,
            clean_name=new_title or None,
            season=task_season if body.media_type == "tv" else None,
            episode=task_episode if body.media_type == "tv" else None,
        )

    # 7. refix_subtitle: 立即触发字幕搜索
    if body.refix_subtitle:
        rebuilt["subtitle"] = "triggered"
        _task_snap = dict(task_record)
        _tmdb_snap = new_tmdb_id
        _imdb_snap = new_imdb_id
        _tp_snap = target_path
        _is_arc = body.is_archive
        _tid = body.task_id
        _mtype = body.media_type

        async def _run_subtitle_now():
            try:
                _db2 = _get_db()
                api_key = _db2.get_config("os_api_key", "").strip()
                ua = _db2.get_config("os_user_agent", "SubtitleHunter v13.2")
                if not api_key:
                    logger.warning("[REBUILD] 未配置 OpenSubtitles API Key，字幕跳过")
                    return
                from app.services.subtitle import SubtitleEngine
                engine = SubtitleEngine(api_key=api_key, user_agent=ua)
                
                # 🛡️ 网络防火墙：为后台字幕任务添加 60 秒超时保护
                try:
                    result = await asyncio.wait_for(
                        engine.download_subtitle_for_task(
                            db_manager=_db2,
                            file_path=_task_snap.get("path") or _tp_snap,
                            tmdb_id=str(_tmdb_snap) if _tmdb_snap else None,
                            media_type=_mtype,
                            imdb_id=_imdb_snap or None,
                            target_path=_tp_snap,
                            archive_id=_tid if _is_arc else None,
                        ),
                        timeout=60.0
                    )
                    logger.info(f"[REBUILD] 字幕搜索完成: task_id={_tid}, result={result}")
                    # 🔧 全表强制终态写入：
                    # - 热表（tasks）：引擎 archive_id=None 不写库，必须手动补写
                    # - 冷表（media_archive）：引擎只在「成功下载」时写 scraped，
                    #   「跳过：本地已有」等分支漏写，此处统一强制覆盖
                    ok = isinstance(result, str) and (
                        result.startswith("成功") or "跳过" in result or "已有" in result
                    )
                    new_sub_status = "scraped" if ok else "missing"
                    try:
                        if not _is_arc and _tid:
                            _db2.update_task_sub_status(_tid, new_sub_status)
                            logger.info(f"[REBUILD] 热表字幕状态已强制更新: task_id={_tid}, sub_status={new_sub_status}")
                        elif _is_arc and _tid:
                            _db2.update_archive_sub_status(
                                _tid,
                                sub_status=new_sub_status,
                                last_check=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                            logger.info(f"[REBUILD] 冷表字幕状态已强制更新: task_id={_tid}, sub_status={new_sub_status}")
                    except Exception as e:
                        logger.error(f"[REBUILD] 字幕状态写库失败: {e}")
                except asyncio.TimeoutError:
                    logger.warning(f"[REBUILD] 字幕搜索超时（60s）: task_id={_tid}")
                    if _tid and _is_arc:
                        try:
                            _db2.update_archive_sub_status(
                                _tid,
                                sub_status="failed",
                                last_check=time.strftime("%Y-%m-%d %H:%M:%S")
                            )
                        except Exception as e:
                            logger.error(f"[REBUILD] 更新字幕状态失败: {e}")
                    elif not _is_arc and _tid:
                        try:
                            _db2.update_task_sub_status(_tid, "failed")
                        except Exception as e:
                            logger.error(f"[REBUILD] 热表超时状态更新失败: {e}")
            except Exception as sub_err:
                logger.error(f"[REBUILD] 字幕搜索失败: {sub_err}")

        background_tasks.add_task(_run_subtitle_now)

    msg_parts = []
    if body.nuclear_reset: msg_parts.append(f"nuclear_cleanup:{'ok' if rebuilt['nuclear'] else 'failed'}")
    if body.refix_nfo:     msg_parts.append(f"nfo:{'ok' if rebuilt['nfo'] else 'failed'}")
    if body.refix_poster:  msg_parts.append(f"poster:{'ok' if rebuilt['poster'] else 'failed'}")
    if body.refix_subtitle: msg_parts.append("subtitle:triggered")

    return {
        "success": True,
        "task_id": body.task_id,
        "title": new_title,
        "tmdb_id": new_tmdb_id,
        "rebuilt": rebuilt,
        "message": "rebuild_complete:" + ";".join(msg_parts) if msg_parts else "no_operation",
    }
