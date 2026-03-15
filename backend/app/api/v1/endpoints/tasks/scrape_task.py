"""
scrape_task.py - 全量刮削任务

包含：
1. perform_scrape_all_task_sync() — 同步刮削执行函数（线程池运行）
2. trigger_scrape_all() — POST /scrape_all 路由
"""
import os
import re
import glob
import asyncio
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.infra.database import get_db_manager
from app.models.domain_media import ScanResponse
from app.services.organizer.hardlinker import SmartLink


def _check_local_subtitles(video_path: str) -> bool:
    """检查视频同级目录下是否存在字幕文件（支持极致模糊匹配）"""
    if not video_path or not os.path.exists(video_path):
        return False
    dir_name = os.path.dirname(video_path)
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    valid_exts = {'.srt', '.ass', '.vtt', '.sub', '.idx'}
    
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
from app.services.metadata.metadata_manager import MetadataManager
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
    """执行全量刮削任务（同步版本，用于线程池执行）"""
    # 🚀 物理级并发防重逻辑：
    # 1. 尝试非阻塞获取锁（blocking=False），若锁已被占用则立即返回，不排队、不等待，直接丢弃冗余请求。
    # 2. 检查内存状态标记位 is_running，确保逻辑与物理锁状态同步（双重防护）。
    # 3. 任务执行完毕后在 finally 块中释放锁，确保即使任务崩溃系统也能自愈。
    if not _scrape_entry_lock.acquire(blocking=False):
        logger.warning("[SCRAPE] ⚠️ 拦截并发请求：已有刮削任务正在运行中，本次触发已丢弃。")
        return

    global scrape_all_status

    try:
        if scrape_all_status["is_running"]:
            return

        scrape_all_status["is_running"] = True
        scrape_all_status["error"] = None

        logger.info("[TMDB] 开始全量刮削任务（线程池模式）...")

        db = get_db_manager()

        # 检查 TMDB API Key 配置（前置检查）
        tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
        if not tmdb_api_key:
            error_msg = "[TMDB] 错误：未配置 API Key，请前往设置页面填写"
            logger.error(error_msg)
            scrape_all_status["error"] = "未配置 TMDB API Key"
            return

        # 读取多语言偏好配置
        poster_lang = db.get_config("poster_lang", "zh")
        rename_lang = db.get_config("rename_lang", "zh")
        logger.info(f"[CONFIG] 海报刮削语言: {poster_lang}, 重命名语言: {rename_lang}")

        # 获取待刮削任务
        tasks_to_scrape = db.get_tasks_needing_scrape()
        count = len(tasks_to_scrape)

        logger.info(f"[TMDB] 发现 {count} 个待刮削任务")

        if count == 0:
            logger.info("[TMDB] 没有待处理的刮削任务")
            scrape_all_status["processed_count"] = 0
            scrape_all_status["last_run_time"] = time.time()
            return

        # 导入刮削引擎
        from app.services.metadata.adapters import TMDBAdapter
        from app.services.ai.agent import AIAgent

        # 初始化刮削器和 AI Agent
        scraper = TMDBAdapter(api_key=tmdb_api_key, rename_lang=rename_lang, poster_lang=poster_lang)
        ai_agent = AIAgent(db)

        logger.info("[AI] AI 决策层已激活，将对所有文件名进行智能提炼")

        # 使用 asyncio.run() 在独立线程中创建隔离事件循环（Python 3.10+ 推荐方式）
        # 避免 get_event_loop() 废弃警告与嵌套 loop 死锁风险

        # 逐个处理任务
        processed = 0
        success_count = 0
        failed_count = 0

        for task in tasks_to_scrape:
            try:
                clean_name = task.get("clean_name", "")
                file_name = task.get("file_name", "")
                file_path = task.get("path", "")
                task_id = task.get("id")
                media_type = task.get("type", "movie")

                logger.info(f"[TMDB] 正在处理: {clean_name or file_name} (ID: {task_id})")

                # ==========================================
                # 🚀 NFO 短路拦截（library 文件零 API 消耗）
                # ==========================================
                # 触发条件：扫描到 library 目录中已有 NFO 文件的媒体
                # 
                # 应用场景：
                # - 用户已使用 Plex/Jellyfin/Emby 刮削过媒体库
                # - 媒体目录中存在 movie.nfo 或 tvshow.nfo
                # - 系统重新扫描时，无需再次调用 TMDB API
                # 
                # 优势：
                # - 零 API 消耗：直接从 NFO 提取 TMDB ID 和 IMDb ID
                # - 零网络延迟：无需等待 TMDB 响应
                # - 保留原有元数据：不覆盖用户手动编辑的信息
                # 
                # NFO 文件位置：
                # - 电影：/media/movies/The Matrix (1999)/movie.nfo
                # - 剧集：/media/tv/Breaking Bad (2008)/tvshow.nfo（注意：在剧集根目录，不在 Season 子目录）
                # ==========================================
                if task.get("status") == "archived" and file_path:
                    _nfo_dir = os.path.dirname(file_path)

                    # 🚀 剧集目录层级修正：NFO 和海报在剧集根目录，而不是 Season 子目录
                    import re as _re_nfo
                    if _re_nfo.match(r'^(Season|S)\s*\d+$|^Specials$', os.path.basename(_nfo_dir), _re_nfo.IGNORECASE):
                        _nfo_dir = os.path.dirname(_nfo_dir)
                    _nfo_path = None
                    for _nfo_name in ["movie.nfo", "tvshow.nfo"]:
                        _candidate = os.path.join(_nfo_dir, _nfo_name)
                        if os.path.exists(_candidate):
                            _nfo_path = _candidate
                            break
                    if _nfo_path:
                        try:
                            import xml.etree.ElementTree as _ET
                            _tree = _ET.parse(_nfo_path)
                            _root = _tree.getroot()
                            _nfo_title   = (_root.findtext("title")  or "").strip()
                            _nfo_year    = (_root.findtext("year")   or "").strip()
                            _nfo_tmdb_id = (_root.findtext("tmdbid") or "").strip()
                            _nfo_imdb_id = (_root.findtext("imdbid") or "").strip()
                            if _nfo_tmdb_id:
                                logger.info(
                                    f"[NFO] 短路拦截成功: task={task_id}, "
                                    f"title='{_nfo_title}', tmdb={_nfo_tmdb_id}, imdb={_nfo_imdb_id}"
                                )
                                # 检查同目录海报
                                _nfo_poster = None
                                for _pn in ["poster.jpg", "poster.png"]:
                                    _pc = os.path.join(_nfo_dir, _pn)
                                    if os.path.exists(_pc):
                                        _nfo_poster = _pc
                                        break
                                
                                # 🚀 致命修复：NFO 解析出的 ID 必须写入数据库（支持双表），并根据本地字幕检测智能设置状态
                                _has_sub = _check_local_subtitles(file_path)
                                _sub_status = "success" if _has_sub else "pending"
                                _is_arc = task.get("is_archive", False)
                                db.update_any_task_metadata(
                                    task_id, 
                                    _is_arc, 
                                    imdb_id=_nfo_imdb_id, 
                                    tmdb_id=_nfo_tmdb_id, 
                                    title=_nfo_title or clean_name, 
                                    year=_nfo_year or None,
                                    sub_status=_sub_status
                                )
                                
                                # 兼容旧逻辑：热表任务仍需调用 update_task_status 触发归档
                                if not _is_arc:
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
                                
                                success_count += 1
                                processed += 1
                                continue
                        except Exception as _nfo_err:
                            logger.warning(f"[NFO] 解析失败，降级走正常刮削流程: {_nfo_err}")

                # 🚀 极致省流：存量库为补 ID 进来的任务，先看有没有字幕（NFO 不存在时才执行）
                if task.get("status") == "archived" and not task.get("imdb_id"):
                    _sub_path = task.get("target_path") or file_path
                    if _sub_path and _check_local_subtitles(_sub_path):
                        logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕，跳过 IMDb ID 补充刮削，节省 Token -> {_sub_path}")
                        _is_arc = task.get("is_archive", False)
                        db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
                        processed += 1
                        continue

                raw_filename = file_name or file_path.split('\\')[-1].split('/')[-1]
                from app.services.scraper.cleaner import MediaCleaner as _MC
                cleaned_filename = _MC(db_manager=db).clean_name(raw_filename)
                if not cleaned_filename:
                    cleaned_filename = raw_filename
                logger.info(f"[RegexLab] 物理正则去噪完成: '{raw_filename}' -> '{cleaned_filename}'")

                # AI 决策层强制注入
                logger.info(f"[AI] 调用 AI Agent 分析文件名: {cleaned_filename}")
                try:
                    ai_result = asyncio.run(ai_agent.ai_identify_media(
                        cleaned_name=cleaned_filename,
                        full_path=file_path,
                        type_hint=media_type
                    ))
                except Exception as ai_err:
                    logger.error(f"[AI] 识别异常: {ai_err}")
                    ai_result = None

                if not ai_result or not isinstance(ai_result, dict):
                    _fallback_query = (cleaned_filename or clean_name or file_name or "").strip()
                    logger.warning(
                        f"[AI][FALLBACK] AI 分析返回 None 或非字典，任务 {task_id} 降级使用 "
                        f"正则清洗名='{_fallback_query}' + db_type='{media_type}'"
                    )
                    ai_result = {
                        "query": _fallback_query,
                        "year": task.get("year", ""),
                        "type": media_type,
                    }

                # ── 路径权威优先：路径已定类型不被 AI 覆盖 ──────────────
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

                # ── 搜索词校验 ────────────────────────────────────────────
                refined_query = (ai_result.get("query") or "").strip()
                if not refined_query:
                    refined_query = (clean_name or file_name or "").strip()
                    logger.warning(
                        f"[AI][FALLBACK] 任务 {task_id}: AI 返回空 query，"
                        f"降级使用 clean_name='{refined_query}'"
                    )

                refined_year = (ai_result.get("year") or task.get("year") or "").strip()

                # ── 年份物理验证：只有文件名中实际存在的年份才能用于 TMDB 过滤 ──
                # 防止 AI 用自身知识推断年份（如 S03 播出年份），导致 TMDB 按错误年份过滤
                from app.services.scraper.cleaner import MediaCleaner as _MCYear
                _year_from_filename = _MCYear().extract_year(raw_filename)
                if refined_year and not _year_from_filename:
                    logger.warning(
                        f"[AI][YEAR_GUARD] 任务 {task_id}: AI 返回 year='{refined_year}' "
                        f"但文件名 '{raw_filename}' 中无年份信息，已清空防止 TMDB 误过滤"
                    )
                    refined_year = ""

                logger.info(
                    f"[AI] 识别完成: query='{refined_query}' | year='{refined_year}' | "
                    f"type='{refined_type}' (db_type='{media_type}')"
                )

                # 使用 AI 提炼后的查询词搜索 TMDB
                if refined_type == "movie":
                    results = scraper.search_movie(query=refined_query, year=refined_year)
                else:
                    results = scraper.search_tv(query=refined_query, year=refined_year)

                # 剧集匹配失败时的二次搜索逻辑
                if (not results or len(results) == 0) and refined_type == "tv":
                    if " " in refined_query:
                        fallback_query = refined_query.split(" ")[0]
                        logger.info(f"[TMDB] 剧集匹配失败，尝试二次搜索: '{fallback_query}'")
                        results = scraper.search_tv(query=fallback_query, year=refined_year)

                if results and len(results) > 0:
                    best_match = results[0]
                    query_lower = refined_query.lower().strip()
                    query_base = re.sub(r'[\s\-]+\d+$', '', query_lower).strip()
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
                    # 设计目标：防止同一媒体被重复入库
                    # 
                    # 问题场景：
                    # - 用户下载了同一部电影的多个版本（蓝光版、导演剪辑版）
                    # - 文件名不同，但 IMDb ID 相同
                    # - 若不拦截，会导致媒体库中出现重复条目
                    # 
                    # 剧集分集防重：
                    # - 同一剧集的不同集数共享 IMDb ID
                    # - 必须精确到 season + episode 才能判断是否重复
                    # - 例如：Breaking Bad S01E01 和 S01E02 有相同的 IMDb ID
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

                        # 🚨🚨🚨 架构师警告：神圣不可侵犯的代码块 (DO NOT REMOVE OR INLINE) 🚨🚨🚨
                        # 当文件被判定为物理重复时，绝对不允许直接 return 或仅仅调用 update_task_status！
                        # 必须调用 mark_task_as_ignored_and_inherit，该方法原子完成两件事：
                        #   1. 跨表查找同源已归档任务的 local_poster_path
                        #   2. 将 ignored 状态 + local_poster_path 一次写入数据库
                        # 若拆分此调用，前端将出现严重破图（VHS 特效丢失 + 白板空图）！
                        db.mark_task_as_ignored_and_inherit(
                            task_id=task_id,
                            imdb_id=imdb_id,
                            media_type=refined_type,
                            season=season_num,
                            episode=episode_num,
                            tmdb_id=int(tmdb_id) if tmdb_id else None,
                        )
                        # 🚨🚨🚨 架构师警告结束 🚨🚨🚨

                        failed_count += 1
                        continue
                    target_path = None
                    local_poster_path = None

                    # ==========================================
                    # 🏥 就地补录检测（In-Place Metadata Injection）
                    # ==========================================
                    # 设计目标：为已存在于媒体库的文件补充元数据，不移动文件
                    # 
                    # 触发条件：
                    # 1. 文件状态为 archived（已归档）
                    # 2. 文件路径位于 library 目录中
                    # 
                    # 应用场景：
                    # - 失忆救援：数据库被清空，但媒体库文件完好
                    # - 元数据补全：用户手动添加文件到媒体库，需要补充 NFO 和海报
                    # - 存量库升级：从其他媒体管理系统迁移过来
                    # 
                    # 就地补录 vs 归档全链路：
                    # - 就地补录：文件已在媒体库，仅写入 NFO 和海报，不移动文件
                    # - 归档全链路：文件在下载目录，需要移动到媒体库并写入元数据
                    # 
                    # 元数据写入位置：
                    # - 电影：/media/movies/The Matrix (1999)/movie.nfo + poster.jpg
                    # - 剧集：/media/tv/Breaking Bad (2008)/tvshow.nfo + poster.jpg（剧集根目录）
                    # ==========================================
                    task_status = task.get("status", "")
                    task_file_path = task.get("path", "")
                    _is_library_file = False

                    # 检查文件是否来自 library 路径
                    all_cfg = db.get_all_config()
                    _lib_paths = [
                        os.path.normpath(p.get("path", "")).lower()
                        for p in all_cfg.get("paths", [])
                        if p.get("type") == "library" and p.get("enabled", False) and p.get("path")
                    ]
                    _file_norm = os.path.normpath(task_file_path).lower()
                    if task_status == "archived" or any(_file_norm.startswith(lp) for lp in _lib_paths):
                        _is_library_file = True

                    # 1. 统一计算 metadata_dir 和 target_path
                    if _is_library_file:
                        # 就地补录模式：文件已在媒体库，不需要移动
                        logger.info(f"[ORG] 就地补录模式：文件来自 library 路径或已归档，仅更新元数据")
                        metadata_dir = os.path.dirname(task_file_path)
                        
                        # 🚀 剧集目录层级修正：必须将 NFO 和海报写在剧集根目录，而不是 Season 文件夹里
                        import re as _re_meta
                        if _re_meta.match(r'^(Season|S)\s*\d+$|^Specials$', os.path.basename(metadata_dir), _re_meta.IGNORECASE):
                            metadata_dir = os.path.dirname(metadata_dir)
                            
                        # 就地补录时，目标路径就是它现在的路径
                        target_path = task_file_path
                    else:
                        # 归档全链路模式：需要移动文件
                        library_root = db.get_active_library_path(refined_type)
                        logger.info(f"[ORG] 媒体库根路径: {library_root}")

                        file_ext = os.path.splitext(file_path)[1]
                        from app.services.scraper.cleaner import MediaCleaner as _MCOrg
                        safe_title = _MCOrg.sanitize_filename(title)
                        logger.info(f"[ORG] 标题净化: '{title}' -> '{safe_title}'")
                        season_num = task.get("season") or 1

                        if refined_type == "movie":
                            folder_name = f"{safe_title} ({year})" if year else safe_title
                            target_dir = os.path.join(library_root, folder_name)
                            target_filename = f"{folder_name}{file_ext}"
                            target_path = os.path.join(target_dir, target_filename)
                            metadata_dir = target_dir
                        else:
                            folder_name = f"{safe_title} ({year})" if year else safe_title
                            season_num = task.get("season") or 1
                            episode_num = task.get("episode") or 1
                            if season_num == 1 and file_path:
                                for _part in Path(file_path).parts:
                                    _m = re.search(r'(?:Season|S)\s*(\d{1,2})\b', _part, re.IGNORECASE)
                                    if _m:
                                        _path_season = int(_m.group(1))
                                        if _path_season != 1:
                                            season_num = _path_season
                                            logger.info(f"[ORG] 从路径补充季号: {file_path} -> season={season_num}")
                                        break
                            season_folder = f"Season {int(season_num)}"
                            show_root_dir = os.path.join(library_root, folder_name)
                            target_dir = os.path.join(show_root_dir, season_folder)
                            metadata_dir = show_root_dir
                            target_filename = f"{folder_name} - S{season_num:02d}E{episode_num:02d}{file_ext}"
                            target_path = os.path.join(target_dir, target_filename)

                        # 物理路径安全检查（路径防穿越校验）
                        try:
                            _resolved_target = Path(target_path).resolve()
                            _resolved_lib = Path(library_root).resolve()
                            _resolved_target.relative_to(_resolved_lib)
                        except ValueError as path_err:
                            logger.error(f"[SECURITY] 路径穿越拦截: {target_path}")
                            db.update_task_status(task_id=task_id, status="failed")
                            failed_count += 1
                            continue

                    logger.info(f"[ORG] 目标路径: {target_path}")

                    # 2. 统一执行防重拦截并提取海报
                    if db.check_task_exists_by_path(target_path):
                        logger.info(f"[SKIP] 目标路径已被存量库占用，拦截重复翻译入库 -> {target_path}")
                        
                        # 🚀 提取已存在文件的海报路径
                        local_poster_path = None
                        for poster_name in ["poster.jpg", "poster.png"]:
                            candidate = os.path.join(metadata_dir, poster_name)
                            if os.path.exists(candidate):
                                local_poster_path = candidate
                                logger.info(f"[SKIP] 复用存量库海报: {local_poster_path}")
                                break
                        
                        db.update_task_title_year(task_id, title, year)
                        _is_arc = task.get("is_archive", False)
                        
                        # 使用双表更新方法
                        if _is_arc:
                            db.update_any_task_metadata(
                                task_id=task_id, 
                                is_archive=True,
                                imdb_id=imdb_id,
                                tmdb_id=str(tmdb_id) if tmdb_id else None,
                                title=title,
                                year=year
                            )
                        
                        # 更新状态为 ignored
                        db.update_task_status(
                            task_id=task_id, 
                            status="ignored", 
                            tmdb_id=int(tmdb_id) if tmdb_id else None,
                            imdb_id=imdb_id,
                            target_path=target_path,
                            local_poster_path=local_poster_path
                        )
                        failed_count += 1
                        processed += 1
                        continue

                    # 3. 如果没被拦截，执行物理操作和元数据写入
                    if _is_library_file:
                        # 就地补录：不移动文件，仅写入元数据
                        season_num = task.get("season") or 1
                        try:
                            meta_manager = MetadataManager(tmdb_api_key, language="zh-CN" if poster_lang == "zh" else "en-US")
                            nfo_filename = "movie.nfo" if refined_type == "movie" else "tvshow.nfo"
                            nfo_path = os.path.join(metadata_dir, nfo_filename)
                            try:
                                nfo_ok = meta_manager.generate_nfo(
                                    tmdb_id=str(tmdb_id),
                                    media_type=refined_type,
                                    output_path=nfo_path,
                                    title=title,
                                    year=year
                                )
                                if nfo_ok:
                                    logger.info(f"[STORAGE] 就地补录 NFO 写入成功: {nfo_path}")
                            except Exception as nfo_err:
                                logger.warning(f"[STORAGE] 就地补录 NFO 生成异常，已跳过: {nfo_err}")

                            try:
                                local_poster_path = meta_manager.download_poster(
                                    tmdb_id=str(tmdb_id),
                                    media_type=refined_type,
                                    output_dir=metadata_dir,
                                    title=title
                                )
                                if local_poster_path:
                                    logger.info(f"[STORAGE] 就地补录海报写入成功: {local_poster_path}")
                            except Exception as poster_err:
                                logger.warning(f"[STORAGE] 就地补录海报下载异常，已跳过: {poster_err}")

                            try:
                                meta_manager.download_fanart(
                                    tmdb_id=str(tmdb_id),
                                    media_type=refined_type,
                                    output_dir=metadata_dir,
                                    title=title
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
                                sub_status="pending",
                                title=title,
                                year=year
                            )
                            success_count += 1
                            processed += 1
                            continue

                    else:
                        # ==========================================
                        # 🚀 归档全链路（Full Archive Pipeline）
                        # ==========================================
                        # 设计目标：将下载目录中的文件归档到媒体库，并补充元数据
                        # 
                        # 完整流程：
                        # 1. 计算目标路径（根据 TMDB 标题和年份）
                        # 2. 创建目标目录
                        # 3. 智能链接（SmartLink）：硬链接 > 软链接 > 复制
                        # 4. 生成 NFO 文件
                        # 5. 下载海报（poster.jpg）
                        # 6. 下载 Fanart（fanart.jpg）
                        # 7. 更新数据库状态
                        # 
                        # 智能链接策略（SmartLink）：
                        # - 优先硬链接：保持做种，节省空间
                        # - 降级软链接：跨文件系统时使用
                        # - 兜底复制：软链接不支持时使用
                        # 
                        # 目标路径规范：
                        # - 电影：/media/movies/The Matrix (1999)/The Matrix (1999).mkv
                        # - 剧集：/media/tv/Breaking Bad (2008)/Season 1/Breaking Bad (2008) - S01E01.mkv
                        # ==========================================
                        try:
                            logger.info(f"[ORG] 源文件路径: {file_path}")

                            os.makedirs(target_dir, exist_ok=True)

                            success, link_type = SmartLink.create_link(file_path, target_path)
                            if success:
                                logger.info(f"[ORG] 归档成功 ({link_type}): {target_path}")

                                if link_type == "already_exists":
                                    logger.info(f"[ORG] 文件已存在，跳过元数据重复下载，直接复用: {target_path}")
                                    local_poster_path = None
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
                                            tmdb_id=str(tmdb_id),
                                            media_type=refined_type,
                                            output_path=nfo_path,
                                            title=title,
                                            year=year
                                        )
                                        if nfo_ok:
                                            logger.info(f"[STORAGE] NFO 写入成功: {nfo_path}")
                                        else:
                                            logger.warning(f"[STORAGE] NFO 写入失败，已跳过: {nfo_path}")
                                    except Exception as nfo_err:
                                        logger.warning(f"[STORAGE] NFO 生成异常，已跳过: {nfo_err}")

                                    local_poster_path = None
                                    try:
                                        local_poster_path = meta_manager.download_poster(
                                            tmdb_id=str(tmdb_id),
                                            media_type=refined_type,
                                            output_dir=metadata_dir,
                                            title=title
                                        )
                                        if local_poster_path:
                                            logger.info(f"[STORAGE] 海报写入成功: {local_poster_path}")
                                        else:
                                            logger.warning(f"[STORAGE] 海报下载失败，DB 写入不受影响")
                                    except Exception as poster_err:
                                        logger.warning(f"[STORAGE] 海报下载异常，已跳过: {poster_err}")

                                    try:
                                        fanart_path = meta_manager.download_fanart(
                                            tmdb_id=str(tmdb_id),
                                            media_type=refined_type,
                                            output_dir=metadata_dir,
                                            title=title
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
                        task_id=task_id,
                        title=title,
                        year=year,
                        season=season_num if refined_type == "tv" else None
                    )
                    db.update_task_status(
                        task_id=task_id,
                        status="archived",
                        tmdb_id=int(tmdb_id),
                        imdb_id=imdb_id if imdb_id else "",
                        target_path=target_path,
                        local_poster_path=local_poster_path,
                        task_type=refined_type
                    )

                    logger.info(f"[TMDB] 已校准任务 {task_id} 的媒体类型为: {refined_type}")

                    # ==========================================
                    # 🎁 字幕白嫖（Local Subtitle Detection）
                    # ==========================================
                    # 设计目标：归档后立即检测本地字幕，避免重复搜索
                    # 
                    # 检测策略：
                    # 1. 严格匹配：视频文件名 + 字幕扩展名（.srt/.ass/.vtt）
                    # 2. 通配匹配：视频文件名.*.srt（支持多语言字幕）
                    # 3. 模糊匹配：同目录下任何字幕文件（电影）或季集号匹配（剧集）
                    # 
                    # 支持的字幕格式：
                    # - .srt（SubRip）
                    # - .ass（Advanced SubStation Alpha）
                    # - .vtt（WebVTT）
                    # - .sub/.idx（VobSub）
                    # 
                    # 优势：
                    # - 零 API 消耗：无需调用 OpenSubtitles API
                    # - 即时反馈：归档后立即显示字幕状态
                    # - 支持手动字幕：用户自行添加的字幕也能识别
                    # ==========================================
                    _sub_check_path = target_path or task_file_path
                    if _sub_check_path and _check_local_subtitles(_sub_check_path):
                        logger.info(f"[SUBTITLE] [白嫖] 发现本地字幕，直接标记 success -> {_sub_check_path}")
                        db.update_task_sub_status(task_id, "success")
                    else:
                        db.update_task_sub_status(task_id, "pending")

                    success_count += 1
                else:
                    db.update_task_status(task_id=task_id, status="failed")
                    failed_count += 1
                    logger.warning(f"[TMDB] 匹配失败: 未找到匹配结果 - {refined_query}")

                processed += 1
                time.sleep(0.3)

            except Exception as e:
                failed_count += 1
                logger.error(f"[TMDB] 匹配失败: {str(e)}")
                try:
                    db.update_task_status(task_id=task.get("id"), status="failed")
                except Exception:
                    pass
                continue

        _update_library_counts()

        scrape_all_status["processed_count"] = processed
        scrape_all_status["last_run_time"] = time.time()

        logger.info(f"[TMDB] 全量刮削完成，已处理 {processed}/{count} 个任务（成功: {success_count}, 失败: {failed_count}）")

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


# ==========================================
# 路由端点
# ==========================================

@router.post("/scrape_all", response_model=ScanResponse)
async def trigger_scrape_all(background_tasks: BackgroundTasks):
    """
    POST /scrape_all - 手动全量刮削
    从数据库中查询所有待刮削任务，逐一调用 TMDB 刮削
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
    GET /scrape_all/status - 获取全量刮削任务状态

    返回字段：
    - is_running: 是否正在运行
    - last_run_time: 上次运行时间（Unix 时间戳）
    - processed_count: 已处理的任务数量
    - error: 错误信息（如果有）
    """
    return {
        "is_running": scrape_all_status["is_running"],
        "last_run_time": scrape_all_status["last_run_time"],
        "processed_count": scrape_all_status["processed_count"],
        "error": scrape_all_status["error"]
    }
