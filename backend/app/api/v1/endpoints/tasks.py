"""
任务管理端点 - Tasks API

提供扫描、刮削、字幕等任务相关的接口
"""
import os
import re
import asyncio
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from app.infra.database import get_db_manager
from app.models.domain_system import SettingsConfig, DeleteBatchRequest, PurgeRequest, ResetSettingsRequest
from app.models.domain_media import ScanResponse
from app.services.organizer.hardlinker import SmartLink
from app.services.metadata.metadata_manager import MetadataManager

logger = logging.getLogger(__name__)


def _update_library_counts():
    """物理扫盘统计媒体库数量，写入数据库缓存。
    由扫描/刮削任务完成后调用，不在 /stats 接口实时执行。
    电影：统计媒体库第一层子文件夹数（每个文件夹=一部电影）
    剧集：递归统计所有视频文件数（每个文件=一集）
    """
    VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".ts", ".flv", ".m2ts"}
    try:
        db = get_db_manager()
        movie_count, tv_count = 0, 0
        paths = db.get_all_config().get("paths", [])
        for p in paths:
            if not p.get("enabled"):
                continue
            folder = p.get("path", "")
            category = p.get("category", "").lower()
            p_type = p.get("type", "").lower()
            if p_type not in ("library", "media") or not folder or not os.path.exists(folder):
                continue
            if category == "movie":
                items = [n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))]
                movie_count += len(items)
            elif category == "tv":
                for root, dirs, files in os.walk(folder):
                    for f in files:
                        if os.path.splitext(f)[1].lower() in VIDEO_EXTS:
                            tv_count += 1
        db.set_config("library_movies_count", movie_count)
        db.set_config("library_tv_count", tv_count)
        logger.info(f"[ORG] 媒体库盘点完成: 电影 {movie_count} 部, 剧集 {tv_count} 集")
    except Exception as e:
        logger.error(f"[ORG] 媒体库盘点失败: {e}")

router = APIRouter()

# 任务状态跟踪
scan_status = {
    "is_running": False,
    "last_scan_time": None,
    "last_scan_count": 0,
    "error": None
}

scrape_all_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}

find_subtitles_status = {
    "is_running": False,
    "last_run_time": None,
    "processed_count": 0,
    "error": None
}


async def perform_scan_task():
    """执行物理扫描任务的后台函数"""
    global scan_status
    
    try:
        scan_status["is_running"] = True
        scan_status["error"] = None
        
        logger.info("[SCAN] 开始执行异步物理扫描任务...")
        
        # 导入扫描器
        from app.services.scraper import ScanEngine
        from pathlib import Path
        import os
        logger.info("[SCAN] ScanEngine 导入成功")
        
        db = get_db_manager()
        logger.info("[SCAN] 数据库管理器获取成功")
        
        # 读取配置：获取所有启用的媒体库路径
        all_config = db.get_all_config()
        logger.info(f"[SCAN] 配置读取成功，配置键: {list(all_config.keys())}")
        
        paths = all_config.get("paths", [])
        logger.info(f"[SCAN] 路径配置数量: {len(paths)}")
        
        # 筛选出 enabled=True 的下载目录（type="download"）并强制规范化路径
        download_paths = [
            str(Path(p.get("path")).resolve()) for p in paths 
            if p.get("enabled", False) and p.get("type") == "download" and p.get("path")
        ]
        logger.info(f"[SCAN] 启用的下载目录（已规范化）: {download_paths}")
        
        # 物理验证路径是否存在
        for path in download_paths:
            exists = os.path.exists(path)
            logger.info(f"[SCAN] 物理检查路径是否存在: {path} -> {exists}")
            if not exists:
                logger.warning(f"[SCAN] 路径不存在，跳过: {path}")
        
        # 过滤掉不存在的路径
        download_paths = [p for p in download_paths if os.path.exists(p)]
        
        if not download_paths:
            logger.info("[SCAN] 未配置任何启用的下载目录或路径不存在，扫描终止")
            logger.warning("[SCAN] 未配置任何启用的下载目录或路径不存在，扫描终止")
            scan_status["is_running"] = False
            scan_status["error"] = "未配置启用的下载目录或路径不存在"
            return
        
        # 读取最小体积过滤阈值，正确处理 0 值
        settings = all_config.get("settings", {})
        settings_dict = settings if isinstance(settings, dict) else {}
        
        # 优先读取 min_size_mb，如果不存在则读取 min_file_size_mb，最后才回退到 50
        min_size_mb = settings_dict.get("min_size_mb")
        if min_size_mb is None:
            min_size_mb = settings_dict.get("min_file_size_mb")
        if min_size_mb is None:
            min_size_mb = 50
        
        # 确保即便是 0 也不会被回退
        min_size_mb = int(min_size_mb)
        logger.info(f"[SCAN] 最小文件体积阈值: {min_size_mb}MB")
        
        # 实例化扫描引擎
        logger.info("[SCAN] 正在初始化 ScanEngine...")
        scan_engine = ScanEngine(max_workers=4, min_size_mb=min_size_mb, db_manager=db)
        logger.info("[SCAN] ScanEngine 初始化完成")
        
        logger.info(f"[SCAN] 扫描配置: 路径数={len(download_paths)}, 最小体积={min_size_mb}MB")
        
        # 触发扫描，获取所有通过 MediaCleaner 洗净的有效媒体文件
        discovered_files = []
        for path in download_paths:
            logger.info(f"[SCAN] 开始扫描路径: {path}")
            files = scan_engine.scan_directory(path, recursive=True)
            logger.info(f"[SCAN] 路径 {path} 发现 {len(files)} 个文件")
            discovered_files.extend(files)
        
        logger.info(f"[SCAN] 扫描完成，总计发现 {len(discovered_files)} 个有效文件")
        
        # 智能入库：遍历扫描结果，检查 tasks 表中是否已存在该路径
        new_count = 0
        for file_info in discovered_files:
            file_path = file_info.get("path")
            
            # 检查是否已存在
            if db.check_task_exists_by_path(file_path):
                logger.debug(f"[SCAN] 文件已存在，跳过: {file_path}")
                continue
            
            # ==========================================
            # 路径配置霸权机制（带混合目录防御）
            # ==========================================
            # 1. 获取正则引擎（MediaCleaner）给出的初步猜测
            is_tv_guess = file_info.get("is_tv", False)
            task_type = "tv" if is_tv_guess else "movie"
            
            # 2. 查找当前文件所属的路径配置
            file_path_normalized = os.path.normpath(file_path).lower()
            matched_path_config = None
            
            for path_cfg in paths:
                if not path_cfg.get("enabled", False):
                    continue
                cfg_path = os.path.normpath(path_cfg.get("path", "")).lower()
                if file_path_normalized.startswith(cfg_path):
                    matched_path_config = path_cfg
                    break
            
            # 3. 路径霸权与混合防御逻辑
            if matched_path_config:
                folder_category = str(matched_path_config.get("category") or "").strip().lower()
                
                # 只有当路径被明确配置为纯粹的 "movie" 或 "tv" 时，才强制覆盖正则结果
                # 如果是 'library', 'mixed', 'download' 等，则维持正则猜测不变
                if folder_category in ["movie", "tv"]:
                    original_type = task_type
                    task_type = folder_category
                    if original_type != task_type:
                        logger.info(f"[SCAN] [路径霸权] 文件 {file_info.get('file_name')} 原类型={original_type}, 路径强制={task_type}")
            
            # 4. 如果因路径霸权被强制认定为 movie，必须清空剧集信息
            season_val = file_info.get("season") if task_type == "tv" else None
            episode_val = file_info.get("episode") if task_type == "tv" else None
            
            # 新文件，执行数据库插入
            task_data = {
                "path": file_path,
                "file_name": file_info.get("file_name"),
                "size": file_info.get("size"),
                "clean_name": file_info.get("clean_name"),
                "year": file_info.get("year"),
                "type": task_type,
                "season": season_val,
                "episode": episode_val,
                "status": "pending"
            }
            
            try:
                db.insert_task(task_data)
                new_count += 1
                logger.info(f"[SCAN] 新文件入库: {file_info.get('clean_name')} (类型: {task_type})")
            except Exception as insert_err:
                logger.error(f"[SCAN] 单条记录插入失败，跳过: {file_info.get('path')} - {insert_err}")
                continue
        
        # 更新状态
        scan_status["is_running"] = False
        scan_status["last_scan_count"] = new_count
        scan_status["last_scan_time"] = time.time()
        
        logger.info(f"[SCAN] 扫描任务完成，新增 {new_count} 条任务记录")
        _update_library_counts()
        
    except Exception as e:
        # 确保异常时重置运行状态，防止按钮卡死
        scan_status["is_running"] = False
        scan_status["error"] = str(e)
        logger.error(f"[ERROR] 扫描任务执行失败: {str(e)}")
        logger.error(f"[SCAN] 扫描任务执行失败: {str(e)}", exc_info=True)


def perform_scrape_all_task_sync():
    """执行全量刮削任务（同步版本，用于线程池执行）"""
    global scrape_all_status
    
    try:
        scrape_all_status["is_running"] = True
        scrape_all_status["error"] = None
        
        logger.info("[TMDB] 开始全量刮削任务（线程池模式）...")
        
        db = get_db_manager()
        
        # 检查 TMDB API Key 配置（前置检查）
        tmdb_api_key = db.get_config("tmdb_api_key", "").strip()
        if not tmdb_api_key:
            error_msg = "[TMDB] 错误：未配置 API Key，请前往设置页面填写"
            logger.error(error_msg)
            print(error_msg)
            scrape_all_status["is_running"] = False
            scrape_all_status["error"] = "未配置 TMDB API Key"
            return
        
        # 获取待刮削任务
        tasks_to_scrape = db.get_tasks_needing_scrape()
        count = len(tasks_to_scrape)
        
        logger.info(f"[TMDB] 发现 {count} 个待刮削任务")
        
        if count == 0:
            logger.info("[TMDB] 没有待处理的刮削任务")
            scrape_all_status["is_running"] = False
            scrape_all_status["processed_count"] = 0
            scrape_all_status["last_run_time"] = time.time()
            return
        
        # 导入刮削引擎
        from app.services.metadata.adapters import TMDBAdapter
        from app.services.ai.agent import AIAgent
        
        # 初始化刮削器和 AI Agent
        scraper = TMDBAdapter(api_key=tmdb_api_key)
        ai_agent = AIAgent(db)
        
        logger.info("[AI] AI 决策层已激活，将对所有文件名进行智能提炼")
        
        # 获取或创建事件循环（线程安全）
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
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
                # 正则军火库：物理级前置拦截器
                # 完全委托给 MediaCleaner.clean_name()：
                #   - 去扩展名
                #   - 去首部发布组标签（[HbT]、[DBD-Raws] 等）
                #   - 执行数据库注入的 filename_clean_regex 规则
                #   - 符号清理与多余空格折叠
                # ==========================================
                raw_filename = file_name or file_path.split('\\')[-1].split('/')[-1]
                from app.services.scraper.cleaner import MediaCleaner as _MC
                cleaned_filename = _MC(db_manager=db).clean_name(raw_filename)
                if not cleaned_filename:
                    cleaned_filename = raw_filename
                logger.info(f"[RegexLab] 物理正则去噪完成: '{raw_filename}' -> '{cleaned_filename}'")
                
                logger.info(f"[RegexLab] 物理正则去噪完成: '{raw_filename}' -> '{cleaned_filename}'")
                
                # AI 决策层强制注入：禁止直接搜索 TMDB
                logger.info(f"[AI] 调用 AI Agent 分析文件名: {cleaned_filename}")
                ai_result = loop.run_until_complete(ai_agent.ai_identify_media(
                    cleaned_name=cleaned_filename,
                    full_path=file_path,
                    type_hint=media_type
                ))
                
                if not ai_result:
                    # AI 彻底失败：优先使用正则清洗名（cleaned_filename），而非原始文件名
                    # cleaned_filename 是经过 RegexLab 物理去噪后的最干净搜索词
                    _fallback_query = (cleaned_filename or clean_name or file_name or "").strip()
                    logger.warning(
                        f"[AI][FALLBACK] AI 分析返回 None，任务 {task_id} 降级使用 "
                        f"正则清洗名='{_fallback_query}' + db_type='{media_type}'"
                    )
                    ai_result = {
                        "query": _fallback_query,
                        "year": task.get("year", ""),
                        "type": media_type,
                    }

                # ── 路径权威优先：路径已定类型不被 AI 覆盖 ──────────────
                # 如果数据库中该任务的 media_type 已经是 movie 或 tv
                # （说明扫描阶段已根据路径配置完成分类），则忽略 AI 返回的 type 字段。
                # 只有当 media_type 为空/未知时，才采纳 AI 的 type 建议。
                ai_suggested_type = (ai_result.get("type") or "").strip().lower()
                if media_type in ("movie", "tv"):
                    # 路径权威：数据库已定类型，强制沿用，拒绝 AI 覆盖
                    refined_type = media_type
                    if ai_suggested_type and ai_suggested_type != media_type:
                        logger.info(
                            f"[AI][PATH_AUTHORITY] 任务 {task_id}: AI 建议 type='{ai_suggested_type}' "
                            f"被路径权威覆盖，强制使用 db_type='{media_type}'"
                        )
                else:
                    # 数据库类型为空/未知，采纳 AI 建议，但仍需二次校验合法性
                    if ai_suggested_type in ("movie", "tv"):
                        refined_type = ai_suggested_type
                    else:
                        refined_type = "movie"  # 终极兜底
                        logger.warning(
                            f"[AI][FALLBACK] 任务 {task_id}: AI 返回非法 type='{ai_suggested_type}'，"
                            f"db_type 为空，最终降级为 'movie'"
                        )

                # ── 搜索词校验：确保 refined_query 不为空 ────────────────
                refined_query = (ai_result.get("query") or "").strip()
                if not refined_query:
                    refined_query = (clean_name or file_name or "").strip()
                    logger.warning(
                        f"[AI][FALLBACK] 任务 {task_id}: AI 返回空 query，"
                        f"降级使用 clean_name='{refined_query}'"
                    )

                refined_year = (ai_result.get("year") or task.get("year") or "").strip()

                logger.info(
                    f"[AI] 识别完成: query='{refined_query}' | year='{refined_year}' | "
                    f"type='{refined_type}' (db_type='{media_type}')"
                )

                # 注意：不再在此处硬编码年份清洗正则
                # 所有正则清洗已由 MediaCleaner.clean_name() 在前面完成
                # refined_query 已经是经过数据库 filename_clean_regex 规则处理的干净搜索词
                
                # 使用 AI 提炼后的查询词搜索 TMDB
                if refined_type == "movie":
                    results = scraper.search_movie(
                        query=refined_query,
                        year=refined_year
                    )
                else:
                    results = scraper.search_tv(
                        query=refined_query,
                        year=refined_year
                    )
                
                # 剧集匹配失败时的二次搜索逻辑（Breaking Bad Pilot 问题修复）
                if (not results or len(results) == 0) and refined_type == "tv":
                    # 尝试剥离第一个空格后的所有内容（如 "Breaking Bad Pilot" -> "Breaking Bad"）
                    if " " in refined_query:
                        fallback_query = refined_query.split(" ")[0]
                        logger.info(f"[TMDB] 剧集匹配失败，尝试二次搜索: '{fallback_query}'")
                        results = scraper.search_tv(
                            query=fallback_query,
                            year=refined_year
                        )
                
                if results and len(results) > 0:
                    # 优先选 original_title / original_name 与搜索词完全匹配的结果
                    # 避免「The Boys」命中「哈迪兄弟」等同名歧义问题
                    best_match = results[0]
                    query_lower = refined_query.lower().strip()
                    # 同时准备一个去掉末尾数字/集号的版本用于宽松匹配
                    query_base = re.sub(r'[\s\-]+\d+$', '', query_lower).strip()
                    for candidate in results:
                        orig = (candidate.get("original_title") or candidate.get("original_name") or "").lower().strip()
                        name = (candidate.get("title") or candidate.get("name") or "").lower().strip()
                        # 严格匹配：original 或 name 与完整搜索词相等
                        if orig == query_lower or name == query_lower:
                            best_match = candidate
                            logger.info(f"[TMDB] 精确匹配: '{candidate.get('title') or candidate.get('name')}'")
                            break
                        # 宽松匹配：去掉末尾集号后匹配（处理 'The Boys 02' → 'The Boys'）
                        if query_base and (orig == query_base or name == query_base):
                            best_match = candidate
                            logger.info(f"[TMDB] 宽松匹配(去集号): '{candidate.get('title') or candidate.get('name')}'")
                            break
                    tmdb_id = best_match.get("id")
                    title = best_match.get("title") or best_match.get("name")
                    release_date = best_match.get("release_date") or best_match.get("first_air_date", "")
                    year = release_date.split("-")[0] if release_date else None

                    logger.info(f"[TMDB] 命中: '{title}' | TMDB_ID={tmdb_id} | 年份={year or 'N/A'} | 类型={refined_type}")

                    # 获取 IMDB ID：优先从详情接口的 external_ids 统一获取
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
                    # N8N V9.1 归档全链路：智能链接 + 元数据补给
                    # ==========================================
                    target_path = None
                    try:
                        # 获取媒体库路径
                        library_root = db.get_active_library_path(refined_type)
                        logger.info(f"[ORG] 媒体库根路径: {library_root}")
                        
                        # 构建目标路径
                        # 电影：/library/Movies/Title (Year)/Title (Year).ext
                        # 剧集：/library/TV/Title (Year)/Season 01/Title (Year) - S01E01.ext
                        file_ext = os.path.splitext(file_path)[1]
                        safe_title = title.replace("/", "-").replace("\\", "-")
                        season_num = task.get("season") or 1  # 兜底初始化，剧集分支会覆盖
                        
                        if refined_type == "movie":
                            folder_name = f"{safe_title} ({year})" if year else safe_title
                            target_dir = os.path.join(library_root, folder_name)
                            target_filename = f"{folder_name}{file_ext}"
                            target_path = os.path.join(target_dir, target_filename)
                            metadata_dir = target_dir  # 电影元数据保存在电影目录
                        else:
                            # 剧集归档
                            folder_name = f"{safe_title} ({year})" if year else safe_title
                            season_num = task.get("season") or 1
                            episode_num = task.get("episode") or 1
                            # 若数据库季号为默认值1，尝试从原始路径补充（修复无S01E01格式文件季号丢失问题）
                            if season_num == 1 and file_path:
                                for _part in Path(file_path).parts:
                                    _m = re.search(r'(?:Season|S)\s*(\d{1,2})\b', _part, re.IGNORECASE)
                                    if _m:
                                        _path_season = int(_m.group(1))
                                        if _path_season != 1:  # 路径明确指定非第1季才覆盖
                                            season_num = _path_season
                                            logger.info(f"[ORG] 从路径补充季号: {file_path} -> season={season_num}")
                                        break
                            season_folder = f"Season {int(season_num)}"
                            show_root_dir = os.path.join(library_root, folder_name)
                            target_dir = os.path.join(show_root_dir, season_folder)
                            metadata_dir = show_root_dir  # 剧集元数据保存在剧集根目录
                            target_filename = f"{folder_name} - S{season_num:02d}E{episode_num:02d}{file_ext}"
                            target_path = os.path.join(target_dir, target_filename)
                        
                        # 物理路径安全检查（路径防穿越校验）
                        from pathlib import Path as _Path
                        try:
                            _resolved_target = _Path(target_path).resolve()
                            _resolved_lib = _Path(library_root).resolve()
                            _resolved_target.relative_to(_resolved_lib)
                        except ValueError:
                            logger.error(f"[SECURITY] 路径穿越攻击拦截！target='{target_path}' 不在 library='{library_root}' 内")
                            target_path = None
                            local_poster_path = None
                            raise ValueError(f"路径穿越拦截: {target_path}")

                        logger.info(f"[ORG] 目标路径: {target_path}")
                        logger.info(f"[ORG] 源文件路径: {file_path}")
                        
                        # 确保目标目录存在
                        logger.info(f"[ORG] 创建目标目录: {target_dir}")
                        os.makedirs(target_dir, exist_ok=True)
                        
                        # 执行智能链接
                        success, link_type = SmartLink.create_link(file_path, target_path)

                        if success:
                            logger.info(f"[ORG] 归档成功 ({link_type}): {target_path}")

                            # 文件已存在（already_exists）说明之前已归档过，跳过元数据重新下载，节省 TMDB API
                            if link_type == "already_exists":
                                logger.info(f"[ORG] 文件已存在，跳过元数据重复下载，直接复用: {target_path}")
                                # 尝试复用已有海报路径
                                local_poster_path = None
                                for poster_name in ["poster.jpg", "poster.png"]:
                                    candidate = os.path.join(metadata_dir, poster_name)
                                    if os.path.exists(candidate):
                                        local_poster_path = candidate
                                        break
                            else:
                                # ==========================================
                                # 原子化元数据生成：NFO + 海报各自独立，互不影响 DB 写入
                                # ==========================================
                                meta_manager = MetadataManager(tmdb_api_key)

                                # 生成 NFO（失败不中断后续流程）
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

                                # 下载海报（失败不中断 DB 写入）
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

                                # 下载背景图（失败不中断 DB 写入）
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
                    
                    # 更新数据库（使用 task_type 参数统一更新类型）
                    # 注意：必须先更新 title/year，再设置 status=archived
                    # 因为 update_task_status(status='archived') 会触发 archive_task() 将记录从 tasks 移走
                    db.update_task_title_year(
                        task_id=task_id,
                        title=title,
                        year=year,
                        season=season_num if refined_type == "tv" else None
                    )
                    db.update_task_status(
                        task_id=task_id,
                        status="archived",
                        tmdb_id=str(tmdb_id),
                        imdb_id=imdb_id if imdb_id else "",
                        target_path=target_path,
                        local_poster_path=local_poster_path,
                        task_type=refined_type
                    )
                    
                    logger.info(f"[TMDB] 已校准任务 {task_id} 的媒体类型为: {refined_type}")
                    
                    success_count += 1
                else:
                    # 匹配失败
                    db.update_task_status(task_id=task_id, status="failed")
                    failed_count += 1
                    logger.warning(f"[TMDB] 匹配失败: 未找到匹配结果 - {refined_query}")
                
                processed += 1
                
                # 避免 API 限流（同步版本）
                time.sleep(0.3)
                
            except Exception as e:
                failed_count += 1
                logger.error(f"[TMDB] 匹配失败: {str(e)}")
                try:
                    db.update_task_status(task_id=task.get("id"), status="failed")
                except:
                    pass
                continue
        
        # --- 物理媒体库盘点（统一函数）---
        _update_library_counts()
        
        scrape_all_status["is_running"] = False
        scrape_all_status["processed_count"] = processed
        scrape_all_status["last_run_time"] = time.time()
        
        logger.info(f"[TMDB] 全量刮削完成，已处理 {processed}/{count} 个任务（成功: {success_count}, 失败: {failed_count}）")
        
    except Exception as e:
        scrape_all_status["is_running"] = False
        scrape_all_status["error"] = str(e)
        logger.error(f"[TMDB] 全量刮削执行失败: {str(e)}")
        # 兜底补救：将因崩溃而卡在 pending 状态的孤儿任务全部标记为 failed
        try:
            db = get_db_manager()
            orphan_tasks = db.get_tasks_needing_scrape()
            for orphan in orphan_tasks:
                db.update_task_status(orphan["id"], "failed")
            if orphan_tasks:
                logger.error(f"[TMDB] 已将 {len(orphan_tasks)} 个孤儿 pending 任务标记为 failed")
        except Exception as rescue_err:
            logger.error(f"[TMDB] 孤儿任务救援失败: {rescue_err}")


def perform_find_subtitles_task_sync():
    """执行全量字幕补完任务（同步版本，用于线程池执行）"""
    global find_subtitles_status
    
    try:
        find_subtitles_status["is_running"] = True
        find_subtitles_status["error"] = None
        
        print("[DEBUG] [API] 开始查找字幕任务（线程池模式）...")
        logger.info("[API] 开始查找字幕任务（线程池模式）...")
        
        db = get_db_manager()
        
        # 获取待字幕任务
        tasks_to_sub = db.get_tasks_needing_subtitles()
        count = len(tasks_to_sub)
        
        if count == 0:
            print("[DEBUG] [API] 没有待处理的字幕任务")
            logger.info("[API] 没有待处理的字幕任务")
            find_subtitles_status["is_running"] = False
            find_subtitles_status["processed_count"] = 0
            find_subtitles_status["last_run_time"] = time.time()
            return
        
        # 获取 OpenSubtitles API 配置
        api_key = db.get_config("os_api_key", "").strip()
        user_agent = db.get_config("os_user_agent", "SubtitleHunter/13.2")
        
        if not api_key:
            print("[DEBUG] [API] 未配置 OpenSubtitles API Key，跳过字幕任务")
            logger.warning("[API] 未配置 OpenSubtitles API Key，跳过字幕任务")
            find_subtitles_status["is_running"] = False
            find_subtitles_status["error"] = "未配置 OpenSubtitles API Key"
            return
        
        # 初始化字幕引擎
        from app.services.subtitle import SubtitleEngine
        subtitle_engine = SubtitleEngine(api_key=api_key, user_agent=user_agent)
        
        # 获取或创建事件循环（线程安全）
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 逐个处理任务
        processed = 0
        for task in tasks_to_sub:
            try:
                file_path = task.get("path")
                tmdb_id = task.get("tmdb_id")
                imdb_id = task.get("imdb_id")
                media_type = task.get("type", "movie")
                target_path = task.get("target_path")
                
                if not file_path or not tmdb_id:
                    print(f"[DEBUG] [SUBTITLE] 任务缺少必要信息，跳过: {task.get('id')}")
                    logger.warning(f"[SUBTITLE] 任务缺少必要信息，跳过: {task.get('id')}")
                    continue
                
                print(f"[DEBUG] [SUBTITLE] 处理任务: {file_path}")
                logger.info(f"[SUBTITLE] 处理任务: {file_path}")
                
                # 调用字幕下载（使用事件循环驱动协程）
                result = loop.run_until_complete(subtitle_engine.download_subtitle_for_task(
                    db_manager=db,
                    file_path=file_path,
                    tmdb_id=tmdb_id,
                    media_type=media_type,
                    imdb_id=imdb_id,
                    target_path=target_path,
                    archive_id=task.get("id")
                ))
                
                print(f"[DEBUG] [SUBTITLE] 结果: {result}")
                logger.info(f"[SUBTITLE] 结果: {result}")
                processed += 1
                
                # 避免 API 限流，每个请求后休眠（同步版本）
                time.sleep(1)
                
            except Exception as e:
                print(f"[DEBUG] [SUBTITLE] 处理任务失败: {str(e)}")
                logger.error(f"[SUBTITLE] 处理任务失败: {str(e)}")
                continue
        
        find_subtitles_status["is_running"] = False
        find_subtitles_status["processed_count"] = processed
        find_subtitles_status["last_run_time"] = time.time()
        
        print(f"[DEBUG] [API] 查找字幕完成，已处理 {processed}/{count} 个任务")
        logger.info(f"[API] 查找字幕完成，已处理 {processed}/{count} 个任务")
        
    except Exception as e:
        find_subtitles_status["is_running"] = False
        find_subtitles_status["error"] = str(e)
        print(f"[DEBUG] [API] 查找字幕执行失败: {str(e)}")
        logger.error(f"[API] 查找字幕执行失败: {str(e)}")


@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(background_tasks: BackgroundTasks):
    """
    POST /scan - 异步触发物理扫描任务
    
    功能说明：
    - 扫描所有配置的下载目录
    - 发现新的媒体文件并入库
    - 应用文件大小过滤和格式白名单
    - 执行文件名清洗和预处理
    """
    global scan_status
    
    if scan_status["is_running"]:
        logger.warning("[API] 扫描任务已在运行中，拒绝重复触发")
        return ScanResponse(message="扫描任务已在运行中，请稍后再试")
    
    try:
        background_tasks.add_task(perform_scan_task)
        logger.info("[API] 物理扫描任务已加入后台队列")
        return ScanResponse(message="扫描任务已启动，正在后台执行")
    except Exception as e:
        logger.error(f"[API] 启动扫描任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动扫描任务失败: {str(e)}")


@router.get("/scan/status")
async def get_scan_status() -> Dict[str, Any]:
    """GET /scan/status - 获取扫描任务状态"""
    return {
        "is_running": scan_status["is_running"],
        "last_scan_time": scan_status["last_scan_time"],
        "last_scan_count": scan_status["last_scan_count"],
        "error": scan_status["error"]
    }


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
        # 将阻塞的同步任务包装到独立线程中运行，避免阻塞事件循环
        async def run_scrape_in_thread():
            await asyncio.to_thread(perform_scrape_all_task_sync)
        
        background_tasks.add_task(run_scrape_in_thread)
        logger.info("[API] 全量刮削任务已加入后台线程队列")
        return ScanResponse(message="全量刮削任务已启动，正在后台线程执行")
    except Exception as e:
        logger.error(f"[API] 启动全量刮削失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动全量刮削失败: {str(e)}")


@router.post("/find_subtitles", response_model=ScanResponse)
async def trigger_find_subtitles(background_tasks: BackgroundTasks):
    """
    POST /find_subtitles - 触发全量待处理字幕补完任务
    
    从数据库中查询所有待字幕任务，逐一调用 OpenSubtitles 搜索并下载
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
    """GET /find_subtitles/status - 获取查找字幕任务状态"""
    return {
        "is_running": find_subtitles_status["is_running"],
        "last_run_time": find_subtitles_status["last_run_time"],
        "processed_count": find_subtitles_status["processed_count"],
        "error": find_subtitles_status["error"]
    }


@router.get("/settings", response_model=SettingsConfig)
async def get_settings():
    """获取完整系统配置"""
    db = get_db_manager()
    config = db.get_all_config()
    
    # 确保返回正确的结构
    if "settings" not in config:
        config["settings"] = {}
    if "paths" not in config:
        config["paths"] = []
    
    return config


@router.post("/settings")
async def update_settings(config: SettingsConfig):
    """
    更新系统配置
    
    功能说明：
    - 接收前端发来的完整配置对象
    - 持久化保存到 config.json
    - 执行 1+1 绝对约束校验（必须有且仅有1个电影库和1个剧集库）
    
    参数：
    - config: 包含 settings 和 paths 的完整配置对象
    
    返回：
    - success: 是否成功
    - message: 操作结果描述
    """
    db = get_db_manager()
    
    # 转换为字典
    config_dict = {
        "settings": config.settings.model_dump(),
        "paths": [p.model_dump() for p in config.paths]
    }
    
    # 防御性编程：先校验，全部通过后才写盘
    # 校验：必须有且仅有1个电影库和1个剧集库（1+1 绝对约束）
    paths = config_dict.get("paths", [])
    active_libs = [
        p for p in paths
        if str(p.get("type", "")).strip().lower() in ["library", "media", "storage"]
        and p.get("enabled", True)
    ]
    movie_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "movie"]
    tv_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "tv"]
    
    if len(movie_libs) > 1 or len(tv_libs) > 1:
        raise HTTPException(
            status_code=400,
            detail="[ERROR] [配置错误] 系统规定同时只能开启 1个电影媒体库 和 1个剧集媒体库！"
        )
    if len(movie_libs) == 0:
        raise HTTPException(
            status_code=400,
            detail="[ERROR] [配置错误] 缺少处于开启状态的 Movie (电影) 媒体库！"
        )
    if len(tv_libs) == 0:
        raise HTTPException(
            status_code=400,
            detail="[ERROR] [配置错误] 缺少处于开启状态的 TV (剧集) 媒体库！"
        )
    
    # 校验全部通过，执行写盘
    try:
        db.save_all_config(config_dict)
        logger.info("[API] 系统配置已更新并持久化")
        return {"success": True, "message": "配置已成功保存"}
    except Exception as e:
        logger.error(f"[API] 保存系统配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存系统配置失败: {str(e)}")


@router.get("")
async def get_all_tasks(search: Optional[str] = None, status: Optional[str] = None, media_type: Optional[str] = None, page: Optional[int] = None, page_size: Optional[int] = None):
    """
    GET /tasks - 获取所有任务列表（支持关键词搜索、状态过滤、媒体类型过滤）
    
    参数：
    - search: 可选，关键词匹配
    - status: 可选，状态过滤（pending/success/failed/archived/all）
    - media_type: 可选，媒体类型过滤（movie/tv）
    - page/page_size: 可选，分页（前端目前传 page_size=99999 做前端分页）
    
    核心修复：将数据库的 type 字段映射为前端期待的 media_type
    archived 状态从 media_archive 表读取，其余从 tasks 表读取
    """
    try:
        from pathlib import Path

        db = get_db_manager()

        # 根据 status 决定查哪张表
        if status == "archived":
            # 只查 media_archive 表
            tasks = db.get_archived_data(search_keyword=search)
            for t in tasks:
                t["status"] = "archived"
        elif status is None or status == "all":
            # 合并 tasks 表 + media_archive 表
            active_tasks = db.get_all_data(search_keyword=search)
            archived_tasks = db.get_archived_data(search_keyword=search)
            for t in archived_tasks:
                t["status"] = "archived"
            tasks = active_tasks + archived_tasks
        else:
            # 查 tasks 表并按状态过滤
            all_tasks = db.get_all_data(search_keyword=search)
            tasks = [t for t in all_tasks if (t.get("status") or "").lower() == status.lower()]

        def _normalize_path(value: Any) -> str:
            """
            将后端内部路径统一转换为 Web 友好的格式：
            - 强制使用正斜杠 `/`
            - 保持原有盘符/前缀，仅修正分隔符
            - 对以 http:// 或 https:// 开头的在线 URL 原样透传，避免被 Path 破坏双斜杠
            """
            if not value:
                return value

            val_str = str(value)
            # 在线 URL 必须原样返回，绝对不能走 Path 解析
            if val_str.startswith("http://") or val_str.startswith("https://"):
                return val_str

            try:
                # Path.as_posix() 会自动把 Windows 反斜杠转换为正斜杠
                return Path(val_str).as_posix()
            except Exception:
                # 兜底：仅替换分隔符，避免抛异常
                return val_str.replace("\\", "/")
        
        # 致命修复：将数据库的 type 映射为前端期待的 media_type，并在下发前统一路径格式
        normalized_tasks = []
        for task in tasks:
            normalized_task = dict(task)

            # 1) 媒体类型对齐：type -> media_type
            media_type_value = str(normalized_task.get("type", "movie")).strip().lower()
            normalized_task["media_type"] = media_type_value

            # 2) 路径字段统一转为 Web 友好格式（正斜杠），避免出现原生 Windows `\`
            for key in ["path", "target_path", "poster_path", "local_poster_path"]:
                if key in normalized_task and normalized_task.get(key):
                    normalized_task[key] = _normalize_path(normalized_task[key])

            # 3) 兼容前端 Task 契约：补充 file_path 别名，指向原始 path
            if "file_path" not in normalized_task:
                normalized_task["file_path"] = normalized_task.get("path") or ""

            normalized_tasks.append(normalized_task)
        
        # media_type 过滤（archived 模式下也生效）
        if media_type and media_type != 'all':
            normalized_tasks = [t for t in normalized_tasks if t.get('media_type') == media_type]

        logger.info(f'[API] 搜索关键词: {search!r}, 返回任务数: {len(normalized_tasks)}')
        return {
            "success": True,
            "count": len(normalized_tasks),
            "tasks": normalized_tasks
        }
    except Exception as e:
        logger.error(f"[API] 获取任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.post("/delete_batch")
async def delete_tasks_batch(body: DeleteBatchRequest):
    """
    POST /tasks/delete_batch - 批量删除任务记录（仅数据库，不删物理文件）
    """
    if not body.ids:
        return {"success": True, "deleted": 0, "message": "未提供任何 ID"}
    
    try:
        db = get_db_manager()
        db.delete_tasks_by_ids(body.ids)
        logger.info(f"[API] 批量删除任务 ids={body.ids}")
        return {"success": True, "deleted": len(body.ids), "message": f"已删除 {len(body.ids)} 条记录"}
    except Exception as e:
        logger.error(f"[API] 批量删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}")
async def delete_task_by_id(task_id: int):
    """
    DELETE /tasks/{task_id} - 单条删除任务记录（仅数据库，不删文件）
    """
    try:
        db = get_db_manager()
        deleted = db.delete_task(task_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="任务不存在或已删除")
        logger.info(f"[API] 已删除任务 id={task_id}")
        return {"success": True, "message": "已删除该任务记录"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge")
async def purge_all_tasks(payload: PurgeRequest):
    """
    DELETE /tasks/purge - 全量清空 tasks 表（核弹按钮）
    仅清空数据库记录，不删物理文件
    
    核心功能：
    1. 清空所有任务记录
    2. 重置自增 ID 计数器
    3. 确保下次插入从 ID 1 开始
    """
    if payload.confirm.strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="请正确输入 CONFIRM")
    
    try:
        db = get_db_manager()
        deleted = db.clear_all_tasks()
        logger.info(f"[OK] [API] 已清空任务表，删除 {deleted} 条记录")
        return {"success": True, "deleted": deleted, "message": f"已清空 {deleted} 条任务记录"}
    except Exception as e:
        logger.error(f"[ERROR] [API] 清空任务表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/retry")
async def retry_task(task_id: int):
    """
    POST /tasks/{task_id}/retry - 重试单个失败的任务
    
    功能说明：
    - 将任务状态重置为 pending
    - 清空错误信息，以便扫描引擎再次处理
    
    参数：
    - task_id: 任务 ID
    
    返回：
    - success: 是否成功
    - message: 操作结果描述
    """
    try:
        db = get_db_manager()
        
        # 直接重置任务状态为 pending（不需要提前检查是否存在）
        db.update_task_status(task_id, "pending")
        
        logger.info(f"[API] 任务 {task_id} 已重置为 pending 状态，等待重新处理")
        return {"success": True, "message": "任务已重置，等待重新处理"}
    except Exception as e:
        logger.error(f"[API] 重试任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")


@router.post("/settings/reset")
async def reset_settings(payload: ResetSettingsRequest):
    """
    POST /tasks/settings/reset - 重置配置为工业级默认值
    
    Args:
        payload: {"target": "ai" | "regex"}
    
    Returns:
        操作结果
    """
    target = payload.target.strip().lower()
    
    if target not in ["ai", "regex"]:
        logger.error(f"[API] 重置配置失败: target 必须为 'ai' 或 'regex'，收到: {target}")
        return {"success": False, "message": "target 必须为 'ai' 或 'regex'"}
    
    try:
        db = get_db_manager()
        db.reset_settings_to_defaults(target)
        
        logger.info(f"[API] 触发配置重置: {target}")
        
        return {
            "success": True,
            "message": f"{target.upper()} 配置已重置为工业级默认值"
        }
    except Exception as e:
        logger.error(f"[API] 配置重置失败: {e}")
        return {"success": False, "message": f"重置失败: {str(e)}"}
