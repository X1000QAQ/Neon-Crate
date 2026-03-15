"""
scan_task.py - 物理扫描任务

包含：
1. perform_scan_task_sync() — 同步扫描执行函数（由 BackgroundTasks 丢入线程池，不阻塞事件循环）
2. trigger_scan() — POST /scan 路由
3. get_scan_status() — GET /scan/status 路由
"""
import os
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.infra.database import get_db_manager
from app.models.domain_media import ScanResponse
from app.api.v1.endpoints.tasks._shared import (
    scan_status,
    _update_library_counts,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 🚀 物理级并发防重锁：防止前端快速连点触发多个扫描任务同时运行。
# 设计选择：使用 threading.Lock 而非 asyncio.Lock，因为任务在同步线程池中执行。
_scan_entry_lock = threading.Lock()


# ==========================================
# 扫描任务执行函数
# ==========================================

def perform_scan_task_sync():
    """
    执行物理扫描任务的同步后台函数。

    设计说明：
    使用普通同步函数而非 async def，FastAPI 的 BackgroundTasks 会自动将其
    投入外部线程池执行，避免大量同步磁盘 I/O 阻塞主事件循环。
    """
    # 🚀 物理级并发防重逻辑：
    # 1. 尝试非阻塞获取锁（blocking=False），若锁已被占用则立即返回，不排队、不等待，直接丢弃冗余请求。
    # 2. 检查内存状态标记位 is_running，确保逻辑与物理锁状态同步（双重防护）。
    # 3. 任务执行完毕后在 finally 块中释放锁，确保即使任务崩溃系统也能自愈。
    if not _scan_entry_lock.acquire(blocking=False):
        logger.warning("[SCAN] ⚠️ 拦截并发请求：已有扫描任务正在运行中，本次触发已丢弃。")
        return

    global scan_status

    try:
        if scan_status["is_running"]:
            return

        scan_status["is_running"] = True
        scan_status["error"] = None

        logger.info("[SCAN] 开始执行物理扫描任务...")

        # 导入扫描器
        from app.services.scraper import ScanEngine
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

        # 筛选出 enabled=True 的媒体库目录（type="library"）
        library_paths = [
            str(Path(p.get("path")).resolve()) for p in paths
            if p.get("enabled", False) and p.get("type") == "library" and p.get("path")
        ]
        logger.info(f"[SCAN] 启用的媒体库目录（已规范化）: {library_paths}")

        # ==========================================
        # 🚀 前置路径与物理 inode 白名单拦截（双重哈希过滤）
        # ==========================================
        # 设计目标：在扫描阶段就拦截已入库文件，避免重复处理
        # 
        # 第一重防护：路径白名单（O(1) 哈希查找）
        # - 收集所有已入库文件的 path 和 target_path
        # - 扫描时直接跳过已知路径，零数据库查询开销
        # 
        # 第二重防护：物理 inode 指纹（终极防重）
        # - 收集媒体库文件的 (inode, size) 指纹
        # - 识别硬链接做种文件：下载目录中与媒体库共享 inode 的文件
        # - 应用场景：qBittorrent 做种 + 硬链接归档，避免重复入库
        # 
        # 性能优化：
        # - 只提取 target_path 的 inode（已归档文件），不扫描 pending 任务
        # - 使用 set 数据结构，查找复杂度 O(1)
        # ==========================================
        logger.info("[SCAN] 正在加载已入库文件路径与物理指纹白名单...")
        known_paths_set = set()
        known_inodes_set = set()
        try:
            # 获取所有任务（含忽略的任务）以构建绝对防护网
            all_tasks = db.get_all_data(include_ignored=True)
            
            # 🎨 优雅的集合推导式：构建路径白名单
            known_paths_set = {
                str(Path(p).resolve())
                for task in all_tasks
                for p in [task.get("path"), task.get("target_path")]
                if p
            }
            
            # 🛡️ 提取存量库的物理 inode 指纹（只提取 target_path，优化性能）
            for task in all_tasks:
                tp = task.get("target_path")
                if tp:  # 只提取已归档的文件（媒体库路径）
                    try:
                        st = os.stat(tp)
                        known_inodes_set.add((st.st_ino, st.st_size))
                    except OSError:
                        pass
            
            logger.info(f"[SCAN] 已加载 {len(known_paths_set)} 条路径，{len(known_inodes_set)} 个物理指纹，开启前置静默过滤")
        except Exception as e:
            logger.warning(f"[SCAN] 加载白名单失败，降级为常规检查: {e}")
            known_paths_set = set()
            known_inodes_set = set()

        # 物理验证路径是否存在
        for path in download_paths + library_paths:
            exists = os.path.exists(path)
            logger.info(f"[SCAN] 物理检查路径是否存在: {path} -> {exists}")
            if not exists:
                logger.warning(f"[SCAN] 路径不存在，跳过: {path}")

        # 过滤掉不存在的路径
        download_paths = [p for p in download_paths if os.path.exists(p)]
        library_paths = [p for p in library_paths if os.path.exists(p)]

        if not download_paths and not library_paths:
            logger.info("[SCAN] 未配置任何启用的目录或路径不存在，扫描终止")
            logger.warning("[SCAN] 未配置任何启用的目录或路径不存在，扫描终止")
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
        # 🚀 落实诊断报告的方案A：并发度拉升至 8
        scan_engine = ScanEngine(
            max_workers=8, 
            min_size_mb=min_size_mb, 
            db_manager=db, 
            known_paths=known_paths_set,
            known_inodes=known_inodes_set
        )
        logger.info("[SCAN] ScanEngine 初始化完成")

        logger.info(f"[SCAN] 扫描配置: 下载目录数={len(download_paths)}, 媒体库目录数={len(library_paths)}, 最小体积={min_size_mb}MB")

        # ==========================================
        # 🔥 物理 inode 熔断机制（硬链接做种文件防重）
        # ==========================================
        # 扫描策略：先扫 library，再扫 download，通过 inode 指纹过滤硬链接
        # 
        # 应用场景：
        # - 用户使用 qBittorrent 下载到 /downloads
        # - 系统通过硬链接将文件归档到 /media（保持做种）
        # - 两个路径指向同一物理文件（共享 inode）
        # - 若不过滤，会导致同一文件被重复入库
        # 
        # 实现原理：
        # 1. 先扫描 library，收集所有文件的 (inode, size) 指纹
        # 2. 再扫描 download，对比 inode 指纹
        # 3. 若 download 中的文件与 library 共享 inode，说明是硬链接，跳过
        # 
        # 为什么不能反过来？
        # - library 文件必须入库（失忆救援机制的基础）
        # - download 文件可以跳过（已通过硬链接归档）
        # ==========================================
        all_scan_batches = []
        library_inodes: set = set()  # (st_ino, st_size) 指纹集合

        # 第一步：先扫 library，建立 inode 指纹库
        if library_paths:
            discovered_library = scan_engine.scan_multiple_directories(library_paths)
            all_scan_batches.append((discovered_library, "archived"))
            logger.info(f"[SCAN] 媒体库目录扫描完成，发现 {len(discovered_library)} 个文件")
            for _f in discovered_library:
                try:
                    _st = os.stat(_f["path"])
                    library_inodes.add((_st.st_ino, _st.st_size))
                except OSError:
                    pass
            logger.info(f"[SCAN] 媒体库 inode 指纹收集完成，共 {len(library_inodes)} 条")

        # 第二步：扫 download，物理 inode 熔断过滤硬链接做种文件
        if download_paths:
            discovered_download_raw = scan_engine.scan_multiple_directories(download_paths)
            discovered_download = []
            for _f in discovered_download_raw:
                try:
                    _st = os.stat(_f["path"])
                    if (_st.st_ino, _st.st_size) in library_inodes:
                        logger.info(f"[SCAN] 🛡️ 物理防重: 下载文件已硬链接至媒体库，跳过 -> {_f['path']}")
                        continue
                except OSError:
                    pass
                discovered_download.append(_f)
            all_scan_batches.append((discovered_download, "pending"))
            logger.info(f"[SCAN] 下载目录扫描完成，发现 {len(discovered_download_raw)} 个文件，物理熔断后剩余 {len(discovered_download)} 个")

        # 智能入库：遍历扫描结果，检查 tasks 表中是否已存在该路径
        new_count = 0
        for discovered_files, default_status in all_scan_batches:
            for file_info in discovered_files:
                file_path = file_info.get("path")

                # 检查是否已存在（路径精确匹配）
                if db.check_task_exists_by_path(file_path):
                    logger.debug(f"[SCAN] 文件已存在，跳过: {file_path}")
                    continue

                # 检查是否已存在（名称防漏，应对 Docker 路径映射偏移）
                _fname = file_info.get("file_name", "")
                _cname = file_info.get("clean_name", "")
                if _fname and _cname and db.check_task_exists_by_name(_fname, _cname):
                    logger.info(f"[SCAN] 🛡️ 映射变更防御: 数据库已存同名文件，跳过双重入库 -> {_fname}")
                    continue

                # ==========================================
                # 🏛️ 路径配置霸权机制（带混合目录防御）
                # ==========================================
                # 设计目标：解决正则引擎误判问题
                # 
                # 问题场景：
                # - 文件名：Avengers.S01E01.mkv（包含 S01E01，正则判定为剧集）
                # - 实际情况：这是电影《复仇者联盟》，文件名是误导性的
                # - 用户已将其放入 /media/movies 目录
                # 
                # 解决方案：路径配置优先级 > 正则引擎猜测
                # - 若文件位于明确配置为 "movie" 的路径，强制类型为 movie
                # - 若文件位于明确配置为 "tv" 的路径，强制类型为 tv
                # - 若路径配置为 "library"/"mixed"/"download"，维持正则猜测
                # 
                # 混合目录防御：
                # - 用户可能将电影和剧集混放在同一目录
                # - 此时不应强制覆盖，而是信任正则引擎的判断
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
                    "status": default_status,  # download→pending，library→archived
                    "target_path": None,
                    "local_poster_path": None,
                }

                # ==========================================
                # 🎁 失忆救援机制（Amnesia Recovery）+ 白嫖逻辑（Eager Binding）
                # ==========================================
                # 触发条件：扫描到 library 目录中的文件（default_status="archived"）
                # 
                # 失忆救援场景：
                # - 数据库被误删或损坏，但媒体库文件完好
                # - 重新扫描时，系统会发现这些"孤儿文件"
                # - 通过目录结构和文件名，自动恢复元数据
                # 
                # 白嫖逻辑（零成本元数据提取）：
                # 1. 从父目录名提取片名和年份
                #    - 标准格式：The Matrix (1999)
                #    - 剧集格式：Breaking Bad (2008)/Season 1/S01E01.mkv
                # 2. 自动绑定本地海报（poster.jpg/poster.png）
                # 3. 直接标记为 archived 状态，跳过刮削流程
                # 4. target_path 设为当前路径（就地归档）
                # 
                # 优势：
                # - 无需重新刮削，节省 API 配额
                # - 保留原有目录结构和海报
                # - 支持 Plex/Jellyfin/Emby 标准命名规范
                # ==========================================
                if default_status == "archived":
                    import re as _re_scan
                    parent_dir = os.path.dirname(file_path)
                    parent_name = os.path.basename(parent_dir)

                    # 🚀 剧集目录层级修正：如果父目录是 Season 文件夹，再向上一级寻找真正的剧集根目录
                    if _re_scan.match(r'^(Season|S)\s*\d+$|^Specials$', parent_name, _re_scan.IGNORECASE):
                        parent_dir = os.path.dirname(parent_dir)
                        parent_name = os.path.basename(parent_dir)
                    # 尝试从父目录名提取「片名 (年份)」结构
                    _dir_match = _re_scan.match(r'^(.+?)\s*\((\d{4})\)\s*$', parent_name)
                    if _dir_match:
                        extracted_name = _dir_match.group(1).strip()
                        extracted_year = _dir_match.group(2).strip()
                        task_data["clean_name"] = extracted_name
                        task_data["year"] = extracted_year
                        logger.info(f"[SCAN] [白嫖] 从目录名提取: clean_name='{extracted_name}', year={extracted_year}")
                    # 检查同级目录是否有 poster.jpg / poster.png
                    for _poster_name in ["poster.jpg", "poster.png"]:
                        _poster_candidate = os.path.join(parent_dir, _poster_name)
                        if os.path.exists(_poster_candidate):
                            task_data["local_poster_path"] = _poster_candidate
                            logger.info(f"[SCAN] [白嫖] 本地海报已绑定: {_poster_candidate}")
                            break
                    # 就地归档：target_path 即为文件当前物理路径
                    task_data["target_path"] = file_path

                try:
                    task_id = db.insert_task(task_data)
                    # 🚀 关键修复：存量库文件插入后，立刻流转至 media_archive 冷表
                    if default_status == "archived" and task_id:
                        try:
                            db.archive_task(task_id)
                            logger.info(f"[SCAN] [生命周期] 存量库文件已流转至 media_archive: task_id={task_id}")
                        except Exception as archive_err:
                            logger.warning(f"[SCAN] [生命周期] archive_task 失败（不影响入库）: {archive_err}")
                    new_count += 1
                    logger.info(f"[SCAN] 新文件入库 (status={default_status}): {file_info.get('clean_name')} (类型: {task_type})")
                except Exception as insert_err:
                    logger.error(f"[SCAN] 单条记录插入失败，跳过: {file_info.get('path')} - {insert_err}")
                    continue

        # 更新状态
        scan_status["last_scan_count"] = new_count
        scan_status["last_scan_time"] = time.time()

        logger.info(f"[SCAN] 扫描任务完成，新增 {new_count} 条任务记录")
        _update_library_counts()

    except Exception as e:
        scan_status["error"] = str(e)
        logger.error(f"[ERROR] 扫描任务执行失败: {str(e)}")
        logger.error(f"[SCAN] 扫描任务执行失败: {str(e)}", exc_info=True)

    finally:
        # 🚀 物理级并发防重逻辑 — 步骤 3：
        # 无论任务正常结束、抛出异常还是遭遇 BaseException，finally 块确保：
        # - is_running 复位为 False，解除前端「运行中」UI 锁定
        # - 释放 threading.Lock，允许下一次任务进入，实现系统自愈
        scan_status["is_running"] = False
        _scan_entry_lock.release()


# ==========================================
# 路由端点
# ==========================================

@router.post("/scan", response_model=ScanResponse)
async def trigger_scan(background_tasks: BackgroundTasks):
    """
    POST /scan - 触发物理扫描任务（后台线程执行）

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
        background_tasks.add_task(perform_scan_task_sync)
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
