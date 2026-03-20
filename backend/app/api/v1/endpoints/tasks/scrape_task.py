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
from app.infra.constants import VIDEO_EXTS_EXTENDED
from app.models.domain_media import ScanResponse
from app.services.organizer.hardlinker import SmartLink
from app.services.metadata.metadata_manager import MetadataManager
from app.services.rebuilder.rebuild_utils import (
    _calc_tv_target_path,
    _check_local_subtitles,
    _cleanup_empty_dirs,
    _get_sibling_episodes,
    _locate_video_for_task,
    _nuclear_clean_directory,
)
from app.api.v1.endpoints.tasks._shared import (
    scrape_all_status,
    _update_library_counts,
)

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

    # 1. [已持物理锁] -> 2. [锁内二次校验 is_running] -> 3. [拦截双窗口竞态后必要时释放锁并退出]
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
        _nfo_showtitle = _nfo.get("showtitle") or ""  # 剧集名（TV 单集 NFO 标准字段）
        _nfo_year    = _nfo.get("year") or ""
        if not _nfo_tmdb_id:
            return False
        # TV 类型：尝试金标准（tvshow.nfo）覆盖单集 episode tmdb_id
        _gold_std = None
        if task.get("type") == "tv":
            from app.services.metadata.nfo_parser import get_tvshow_gold_standard as _get_gold_std
            _gold_std = _get_gold_std(file_path)
        if _gold_std:
            _nfo_tmdb_id = _gold_std.get("tmdb_id") or _nfo_tmdb_id
            _nfo_imdb_id = _gold_std.get("imdb_id") or _nfo_imdb_id
            _nfo_year    = _gold_std.get("year") or _nfo_year
            final_title  = _gold_std.get("title") or _nfo_showtitle or task.get("title") or clean_name or _nfo_title
        else:
            if task.get("type") == "tv":
                final_title = _nfo_showtitle or task.get("title") or clean_name or _nfo_title
            else:
                final_title = _nfo_title or clean_name
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
        _sub_status = "scraped"
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(
            task_id, _is_arc,
            imdb_id=_nfo_imdb_id,
            tmdb_id=_nfo_tmdb_id,
            title=final_title,
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
                title=final_title,
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
    _cleaner = _MC(db_manager=db)

    # ── 保护性提取：在任何正则删除之前，先物理提取 Season/Episode ──
    # 目的：防止 clean_name() 把集数信息（如 E14）误删，
    # 导致 AI 无法获得准确 Episode，进而触发 IMDb 查重熔断。
    _pre_season, _pre_episode = _cleaner.extract_season_episode(raw_filename)
    if _pre_season is not None or _pre_episode is not None:
        logger.info(
            f"[RegexLab] 保护性提取命中: S={_pre_season} E={_pre_episode} "
            f"(来自原始文件名: '{raw_filename}')"
        )
        # 将提取结果回写到 task dict，后续所有步骤优先使用这个值
        if _pre_season is not None and task.get("season") is None:
            task["season"] = _pre_season
        if _pre_episode is not None and task.get("episode") is None:
            task["episode"] = _pre_episode

    cleaned_filename = _cleaner.clean_name(raw_filename)
    if not cleaned_filename:
        cleaned_filename = raw_filename
    logger.info(f"[RegexLab] 物理正则去噪完成: '{raw_filename}' -> '{cleaned_filename}'")

    # ── 构建 AI 提示锚点：若已确定 S/E，注入到 AI 提示中强制锁定 ──
    _locked_season  = task.get("season")
    _locked_episode = task.get("episode")

    # 业务链路：1. 调用 AI Agent 分析文件名 -> 2. 提取查询词、年份、类型
    logger.info(f"[AI] 调用 AI Agent 分析文件名: {cleaned_filename}")
    try:
        # 1. 异步调用 AI Agent 进行媒体识别（传入锁定的季集号防止 AI 丢弃）
        ai_result = asyncio.run(ai_agent.ai_identify_media(
            cleaned_name=cleaned_filename,
            full_path=file_path,
            type_hint=media_type,
            locked_season=_locked_season,
            locked_episode=_locked_episode,
        ))
    except Exception as ai_err:
        logger.error(f"[AI] 引擎不可用或识别异常，触发 Fail-Fast: {ai_err}")
        raise RuntimeError(f"ai_engine_unavailable: {ai_err}") from ai_err

    # 2. AI 返回结构校验（Fail-Fast：不允许正则兜底继续跑 TMDB）
    if not ai_result or not isinstance(ai_result, dict):
        logger.error(
            f"[AI] 引擎不可用或识别彻底失败，触发 Fail-Fast: task_id={task_id}, "
            f"ai_result_type={type(ai_result)}"
        )
        raise RuntimeError("ai_engine_unavailable: invalid_ai_result")

    # ── 季集锁定护盾：正则预提取结果强制覆盖 AI 输出 ──
    # 若正则已明确提取到 S/E，AI 无权修改或丢弃这两个值
    if _locked_season is not None:
        if ai_result.get("season") != _locked_season:
            logger.info(
                f"[AI][LOCK] 季号锁定：AI 返回 season={ai_result.get('season')}，"
                f"强制覆盖为正则提取值 season={_locked_season}"
            )
        ai_result["season"] = _locked_season
    if _locked_episode is not None:
        if ai_result.get("episode") != _locked_episode:
            logger.info(
                f"[AI][LOCK] 集号锁定：AI 返回 episode={ai_result.get('episode')}，"
                f"强制覆盖为正则提取值 episode={_locked_episode}"
            )
        ai_result["episode"] = _locked_episode

    # 将锁定后的季集号同步回 task dict（供后续步骤使用）
    if ai_result.get("season") is not None:
        task["season"] = ai_result["season"]
    if ai_result.get("episode") is not None:
        task["episode"] = ai_result["episode"]

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
    # Fail-Fast：AI 返回空 query 直接中断，不允许降级使用 clean_name 继续跑 TMDB
    refined_query = (ai_result.get("query") or "").strip()
    if not refined_query:
        logger.error(f"[AI] AI 返回空 query，触发 Fail-Fast: task_id={task_id}")
        raise RuntimeError("ai_engine_unavailable: empty_query")

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

    # ── 搜索降级策略 ────────────────────────────────────────────────
    # 第一梯队（精确）：Title + Year（已在上方执行）
    # 第二梯队（容错）：Title 完整片名，移除 Year（AI 幻觉年份时拯救正确片名）
    if (not results or len(results) == 0) and refined_type == "tv" and refined_year:
        # 第二梯队：保留完整片名，移除年份限定
        logger.info(f"[TMDB] 剧集匹配失败（第一梯队），第二梯队：完整片名无年份搜索: '{refined_query}'")
        results = scraper.search_tv(query=refined_query, year=None)

    if not results or len(results) == 0:
        logger.warning(f"[TMDB] 搜索 0 结果，拒绝猜测，任务中断: {refined_query}")
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

    # ── TV 集号防重护盾 ──
    # 当 type='tv' 且 episode 为空时，跳过 [SKIP] 逻辑，进入待定状态。
    # 原因：缺少 episode 无法精确判断是否重复，强行拦截会导致漏入库。
    if refined_type == "tv" and episode_num is None:
        logger.info(
            f"[DUP_CHECK] 任务 {task_id}: type='tv' 但 episode=None，"
            f"跳过重复检测，进入待定状态（防止误拦截）。"
        )
        # 不执行 check_media_exists，直接返回正常流程继续处理
    elif imdb_id and db.check_media_exists(imdb_id, refined_type, season_num, episode_num):
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
                sub_status="scraped",
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
            sub_status="scraped",
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
            # ── 单集 NFO（仅剧集）────────────────────────────────────
            if refined_type == "tv" and episode_num and season_num:
                try:
                    ep_nfo_path = str(Path(task_file_path).with_suffix(".nfo"))
                    ep_ok = meta_manager.generate_episode_nfo(
                        tmdb_id=str(tmdb_id),
                        season=int(season_num),
                        episode=int(episode_num),
                        output_path=ep_nfo_path,
                        title=title,
                    )
                    if ep_ok:
                        logger.info(f"[STORAGE] 就地补录单集 NFO 写入成功: {ep_nfo_path}")
                except Exception as ep_nfo_err:
                    logger.warning(f"[STORAGE] 就地补录单集 NFO 生成异常，已跳过: {ep_nfo_err}")
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
                    # ── 单集 NFO（仅剧集）────────────────────────────────────
                    # 文件名对齐：与 target_path 同名，仅后缀改为 .nfo
                    if refined_type == "tv" and episode_num and season_num:
                        try:
                            ep_nfo_path = str(Path(target_path).with_suffix(".nfo"))
                            ep_ok = meta_manager.generate_episode_nfo(
                                tmdb_id=str(tmdb_id),
                                season=int(season_num),
                                episode=int(episode_num),
                                output_path=ep_nfo_path,
                                title=title,
                            )
                            if ep_ok:
                                logger.info(f"[STORAGE] 单集 NFO 写入成功: {ep_nfo_path}")
                            else:
                                logger.warning(f"[STORAGE] 单集 NFO 写入失败，已跳过: {ep_nfo_path}")
                        except Exception as ep_nfo_err:
                            logger.warning(f"[STORAGE] 单集 NFO 生成异常，已跳过: {ep_nfo_err}")
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
                db.update_any_task_metadata(task_id, task.get("is_archive", False), sub_status="scraped")
                return True, False

        # 3. AI 提炼（Fail-Fast：AI 不可用时直接失败落库，不进入 TMDB）
        try:
            refined_query, refined_year, refined_type = _step_ai_extraction(
                db, ai_agent, task, task_id, file_name, file_path, clean_name, media_type
            )
        except Exception as ai_fail:
            logger.error(f"[AI] 引擎不可用或识别彻底失败，触发 Fail-Fast: {ai_fail}")
            try:
                db.update_task_status(task_id=task_id, status="failed")
            except Exception:
                pass
            try:
                db.update_any_task_metadata(task_id, task.get("is_archive", False), sub_status="failed")
            except Exception:
                try:
                    db.update_task_sub_status(task_id, "failed")
                except Exception:
                    pass
            return False, True

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
        # 3. 若发现本地字幕则标记为 scraped -> 4. 否则标记为 pending（等待搜索）
        #
        # 优势：零 API 消耗，归档后立即显示字幕状态，支持手动字幕
        _sub_check_path = target_path or file_path
        if _sub_check_path and _check_local_subtitles(
            _sub_check_path,
            sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))
        ):
            # ── Step 1: 发现本地字幕 ──
            # 业务链路：1. 记录日志 -> 2. 更新 sub_status 为 scraped -> 3. 跳过后续字幕搜索
            logger.info(f"[SUBTITLE] [白嫖] 发现本地字幕，直接标记 scraped -> {_sub_check_path}")
            db.update_task_sub_status(task_id, "scraped")
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
        try:
            db.update_any_task_metadata(task.get("id"), task.get("is_archive", False), sub_status="failed")
        except Exception:
            try:
                db.update_task_sub_status(task.get("id"), "failed")
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


def _parse_video_exts(raw: str) -> frozenset:
    """将逗号分隔的后缀字符串解析为小写 frozenset。"""
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts) if parts else VIDEO_EXTS_EXTENDED


def _parse_sub_exts(raw: str) -> frozenset:
    """将逗号分隔的字幕后缀字符串解析为小写 frozenset。"""
    _fallback = frozenset({'.srt', '.ass', '.vtt', '.sub', '.idx'})
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts) if parts else _fallback
