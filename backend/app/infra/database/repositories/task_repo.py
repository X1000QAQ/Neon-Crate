"""
task_repo.py - 任务仓储

职责：管理 tasks 表的全生命周期 CRUD，包含任务创建、状态流转、查询、删除。

迁入方法（原 db_manager.py）：
  - add_task                        (原行 440)
  - insert_task                     (原行 485)
  - is_processed                    (原行 450)
  - get_task_id_by_path             (原行 457)
  - get_task_status_by_path         (原行 465)
  - check_task_exists_by_path       (原行 473)
  - update_task_status              (原行 504)
  - update_task_title_year          (原行 544)
  - get_tasks_needing_scrape        (原行 640)
  - get_tasks_needing_subtitles     (原行 650)
  - reset_orphan_pending_tasks      (原行 976)
  - delete_tasks_by_ids             (原行 921)
  - delete_task                     (原行 940)
  - clear_all_tasks                 (原行 959)
  - delete_tasks_and_archive_by_ids (原行 829)
  - delete_task_and_archive_by_id   (原行 877)

Impact 分析（2026-03-12）：
  update_task_status        → CRITICAL (2 direct: perform_scrape_all_task_sync + retry_task)
  get_tasks_needing_scrape  → HIGH     (1 direct: perform_scrape_all_task_sync)
  insert_task               → LOW      (1 direct: perform_scan_task → cron_scanner_loop)
  迁移安全：外观层接口不变，所有调用方零感知。

跨域依赖：
  update_task_status 在 status='archived' 时调用 archive_task（ArchiveRepo）。
  采用方案A：构造注入 archive_repo，避免循环依赖。
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from .base import BaseRepository

logger = logging.getLogger(__name__)


class TaskRepo(BaseRepository):
    """任务仓储：管理 tasks 表的全生命周期 CRUD"""

    def __init__(self, get_conn_fn, db_lock, config_path: str = "data/config.json",
                 secure_keys_path: str = "data/secure_keys.json", archive_repo=None):
        """
        Args:
            archive_repo: ArchiveRepo 实例，用于 update_task_status 在
                          status='archived' 时触发归档。可通过 set_archive_repo() 延迟注入。
        """
        super().__init__(get_conn_fn, db_lock, config_path, secure_keys_path)
        self._archive_repo = archive_repo

    def set_archive_repo(self, archive_repo):
        """延迟注入 archive_repo（解决初始化顺序依赖）"""
        self._archive_repo = archive_repo

    # ==========================================
    # 任务创建
    # ==========================================

    def add_task(self, path: str, filename: str, clean_name: str, type_hint: str):
        """添加任务（旧版接口，兼容保留）"""
        with self.db_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO tasks (path, file_name, clean_name, type, status) "
                "VALUES (?, ?, ?, ?, 'pending')",
                (path, filename, clean_name, type_hint)
            )
            conn.commit()

    def insert_task(self, task_data: Dict[str, Any]) -> int:
        """插入新任务记录（新版，接受 Dict，支持 local_poster_path / target_path / tmdb_id / imdb_id，返回新记录 ID）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "INSERT INTO tasks "
                "(path, file_name, clean_name, type, status, year, season, episode, local_poster_path, target_path, tmdb_id, imdb_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_data.get("path"),
                    task_data.get("file_name"),
                    task_data.get("clean_name"),
                    task_data.get("type", "movie"),
                    task_data.get("status", "pending"),
                    task_data.get("year"),
                    task_data.get("season"),
                    task_data.get("episode"),
                    task_data.get("local_poster_path"),
                    task_data.get("target_path"),
                    task_data.get("tmdb_id"),
                    task_data.get("imdb_id"),
                )
            )
            conn.commit()
            return cursor.lastrowid

    # ==========================================
    # 任务查询
    # ==========================================

    def is_processed(self, file_path: str) -> bool:
        """检查文件是否已处理（tasks 表中存在）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT 1 FROM tasks WHERE path = ? LIMIT 1", (file_path,)
            )
            return cursor.fetchone() is not None

    def get_task_id_by_path(self, file_path: str) -> Optional[int]:
        """根据路径获取任务 ID"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id FROM tasks WHERE path = ? LIMIT 1", (file_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def get_task_status_by_path(self, file_path: str) -> Optional[str]:
        """根据路径获取任务状态"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT status FROM tasks WHERE path = ? LIMIT 1", (file_path,)
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def check_task_exists_by_path(self, file_path: str) -> bool:
        """检查指定路径的任务是否已存在（同时检查 tasks 和 media_archive 两张表，含 target_path 盲区防御）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT 1 FROM tasks WHERE path = ? LIMIT 1", (file_path,)
            )
            if cursor.fetchone() is not None:
                return True
            # 同时比对 path 和 target_path，防止硬链接文件被重复入库
            cursor = conn.execute(
                "SELECT 1 FROM media_archive WHERE path = ? OR target_path = ? LIMIT 1",
                (file_path, file_path)
            )
            return cursor.fetchone() is not None

    def check_task_exists_by_name(self, file_name: str, clean_name: str) -> bool:
        """
        基于文件名的防重检查（应对 Docker 路径映射偏移场景）

        使用场景：
        - Docker 容器内外路径映射不一致（如 /downloads vs /mnt/downloads）
        - 文件被移动或重命名后，路径防重失效
        - 需要通过文件名本身判断是否已处理

        双重策略：
        1. 精确匹配原始文件名 + clean_name（防止 S01E01 等通用名误杀）
        2. target_path 后缀匹配（匹配媒体库重命名后的文件）
        
        返回：
            True: 文件已存在（跳过处理）
            False: 文件不存在（可以入库）
        """
        if not file_name or not clean_name:
            return False
        with self.db_lock:
            conn = self._get_conn()
            # 策略1：精确匹配 file_name + clean_name（tasks 表）
            cursor = conn.execute(
                "SELECT 1 FROM tasks WHERE file_name = ? AND clean_name = ? LIMIT 1",
                (file_name, clean_name)
            )
            if cursor.fetchone() is not None:
                return True
            # 策略1：精确匹配 file_name + clean_name（media_archive 表）
            cursor = conn.execute(
                "SELECT 1 FROM media_archive WHERE file_name = ? AND clean_name = ? LIMIT 1",
                (file_name, clean_name)
            )
            if cursor.fetchone() is not None:
                return True
            # 策略2：target_path 后缀匹配（兼容 Unix / Windows 路径分隔符）
            unix_suffix = f"%/{file_name}"
            win_suffix = f"%\\{file_name}"
            cursor = conn.execute(
                "SELECT 1 FROM tasks WHERE target_path LIKE ? OR target_path LIKE ? LIMIT 1",
                (unix_suffix, win_suffix)
            )
            if cursor.fetchone() is not None:
                return True
            cursor = conn.execute(
                "SELECT 1 FROM media_archive WHERE target_path LIKE ? OR target_path LIKE ? LIMIT 1",
                (unix_suffix, win_suffix)
            )
            return cursor.fetchone() is not None

    def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
        """
        获取需要刮削的任务列表（双表联查：tasks 热表 + media_archive 冷表）
        
        ── 业务链路 ──
        1. 查询热表 tasks（pending 或 archived 缺 imdb_id 的任务）-> 
        2. 查询冷表 media_archive（缺 imdb_id 的归档任务）-> 
        3. 去重（冷表中已在热表的任务不重复返回）-> 
        4. 返回合并结果（包含 is_archive 标记）
        
        刮削条件：
        1. tasks 热表：status='pending' 的新任务
        2. tasks 热表：status='archived' 但缺少 imdb_id 且字幕未完成的任务
        3. media_archive 冷表：缺少 imdb_id 且字幕未完成的归档任务
        
        返回：
            List[Dict]: 任务列表，包含 is_archive 标记（True=冷表，False=热表）
        """
        with self.db_lock:
            conn = self._get_conn()
            
            # ── Step 1: 查询热表 tasks ──
            # 业务链路：1. 查询 status='pending' 的新任务 -> 2. 查询 status='archived' 但缺 imdb_id 的任务 -> 
            # 3. 按创建时间排序 -> 4. 标记 is_archive=0（热表）
            cursor = conn.execute(
                """
                SELECT id, path, file_name, clean_name, type, status, season, episode,
                       imdb_id, tmdb_id, target_path, sub_status, 0 as is_archive
                FROM tasks
                WHERE status = 'pending'
                   OR (status = 'archived'
                       AND (imdb_id IS NULL OR imdb_id = '')
                       AND (sub_status IS NULL OR sub_status NOT IN ('scraped', 'found')))
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            results = [
                {
                    "id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3],
                    "type": r[4], "status": r[5], "season": r[6], "episode": r[7],
                    "imdb_id": r[8], "tmdb_id": r[9], "target_path": r[10], "sub_status": r[11],
                    "is_archive": False
                }
                for r in rows
            ]
            
            # ── Step 2: 查询冷表 media_archive ──
            # 业务链路：1. 查询缺 imdb_id 的归档任务 -> 2. 将 original_task_id 映射为 id（与热表保持一致）-> 
            # 3. 标记 is_archive=1（冷表）-> 4. 去重（排除已在热表中的任务）
            seen_paths = {r["target_path"] for r in results if r.get("target_path")}
            cursor2 = conn.execute(
                """
                SELECT original_task_id AS id, path, file_name, '' as clean_name, type, 'archived' as status,
                       NULL as season, NULL as episode,
                       imdb_id, tmdb_id, target_path, sub_status, 1 as is_archive
                FROM media_archive
                WHERE (imdb_id IS NULL OR imdb_id = '')
                  AND (sub_status IS NULL OR sub_status NOT IN ('scraped', 'found'))
                  AND (target_path IS NOT NULL AND target_path != '')
                ORDER BY archived_at ASC
                """
            )
            for r in cursor2.fetchall():
                tp = r[10]
                # 5. 去重：若冷表任务的 target_path 已在热表中，则跳过
                if tp and tp in seen_paths:
                    continue
                results.append({
                    "id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3],
                    "type": r[4], "status": r[5], "season": r[6], "episode": r[7],
                    "imdb_id": r[8], "tmdb_id": r[9], "target_path": r[10], "sub_status": r[11],
                    "is_archive": True
                })
                if tp:
                    seen_paths.add(tp)
            return results

    def get_tasks_needing_subtitles(self) -> List[Dict[str, Any]]:
        """
        获取需要字幕的任务列表（含 7 天冷却期过滤，双表联查）
        
        ── 业务链路 ──
        1. 查询冷表 media_archive（已归档但字幕未完成的任务）-> 
        2. 查询热表 tasks（已归档但字幕未完成的任务）-> 
        3. 按 target_path 去重（冷表优先）-> 
        4. 应用 7 天冷却期过滤（避免频繁搜索无字幕的冷门片源）-> 
        5. 返回合并结果（包含 is_archive 标记）
        
        字幕条件：
        1. 必须有 imdb_id（用于字幕搜索）
        2. 必须有 target_path（已归档到媒体库）
        3. sub_status 为 pending/failed/missing/NULL
        4. 若 sub_status='missing'，需距上次检查超过 7 天（冷却期）
        
        冷却期设计：
        - 避免频繁搜索无字幕的冷门片源
        - 7 天后重试，给字幕组时间上传
        
        返回：
            List[Dict]: 任务列表，包含 is_archive 标记（True=冷表，False=热表）
        """
        with self.db_lock:
            conn = self._get_conn()
            # ── Step 1: 计算冷却期截止时间 ──
            # 业务链路：1. 获取当前时间 -> 2. 减去 7 天 -> 3. 格式化为 SQL 时间戳
            cooldown_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            
            # ── Step 2: 查询冷表 media_archive ──
            # 业务链路：1. 查询已归档的任务 -> 2. 过滤条件：有 target_path + 有 imdb_id -> 
            # 3. 字幕状态为 pending/failed/missing 或 NULL -> 4. 若为 missing 则检查冷却期 -> 
            # 5. 标记 is_archive=True
            cursor = conn.execute(
                "SELECT original_task_id AS id, path, file_name, type, tmdb_id, imdb_id, target_path, sub_status "
                "FROM media_archive "
                "WHERE (target_path IS NOT NULL AND target_path != '') "
                "  AND (imdb_id IS NOT NULL AND imdb_id != '') "
                "AND (sub_status IN ('pending', 'failed') OR sub_status IS NULL "
                "     OR (sub_status = 'missing' AND (archived_at IS NULL OR archived_at < ?))) "
                "ORDER BY archived_at ASC",
                (cooldown_date,)
            )
            rows = cursor.fetchall()
            results = [
                {
                    "id": r[0], "path": r[1], "file_name": r[2], "type": r[3],
                    "tmdb_id": r[4], "imdb_id": r[5], "target_path": r[6], "sub_status": r[7],
                    "is_archive": True
                }
                for r in rows
            ]
            
            # ── Step 3: 查询热表 tasks ──
            # 业务链路：1. 查询已归档的任务 -> 2. 过滤条件：有 target_path + 有 imdb_id -> 
            # 3. 字幕状态为 NULL 或非（已完成：scraped/found）-> 4. 标记 is_archive=False
            cursor2 = conn.execute(
                "SELECT id, path, file_name, type, tmdb_id, imdb_id, target_path, sub_status "
                "FROM tasks "
                "WHERE status = 'archived' "
                "  AND (target_path IS NOT NULL AND target_path != '') "
                "  AND (imdb_id IS NOT NULL AND imdb_id != '') "
                "  AND (sub_status IS NULL OR sub_status NOT IN ('scraped', 'found')) "
                "ORDER BY created_at ASC"
            )
            rows2 = cursor2.fetchall()
            
            # ── Step 4: 合并去重 ──
            # 业务链路：1. 按 target_path 去重 -> 2. 冷表记录优先保留 -> 
            # 3. 热表中重复的记录被跳过 -> 4. 返回最终合并结果
            seen_targets = {r["target_path"] for r in results if r.get("target_path")}
            for r in rows2:
                tp = r[6]
                # 1. 若热表任务的 target_path 已在冷表中，则跳过（冷表优先）
                if tp and tp in seen_targets:
                    continue
                results.append({
                    "id": r[0], "path": r[1], "file_name": r[2], "type": r[3],
                    "tmdb_id": r[4], "imdb_id": r[5], "target_path": r[6], "sub_status": r[7],
                    "is_archive": False
                })
                # 2. 将热表任务的 target_path 添加到去重集合
                if tp:
                    seen_targets.add(tp)
            return results

    # ==========================================
    # 任务状态更新
    # ==========================================

    def update_task_status(
        self,
        task_id: int,
        status: Optional[str] = None,
        tmdb_id: Optional[str] = None,
        imdb_id: Optional[str] = None,
        target_path: Optional[str] = None,
        sub_status: Optional[str] = None,
        last_sub_check: Optional[str] = None,
        local_poster_path: Optional[str] = None,
        task_type: Optional[str] = None,
        archive_repo=None,
    ):
        """
        更新任务状态。
        当 status='archived' 时自动触发归档（移入 media_archive）。
        archive_repo 优先使用参数传入，其次使用构造注入的 self._archive_repo。
        """
        with self.db_lock:
            conn = self._get_conn()
            updates = []
            params = []
            if status is not None:
                updates.append("status = ?"); params.append(status)
            if tmdb_id is not None:
                updates.append("tmdb_id = ?"); params.append(tmdb_id)
            if imdb_id is not None:
                updates.append("imdb_id = ?"); params.append(imdb_id)
            if target_path is not None:
                updates.append("target_path = ?"); params.append(target_path)
            if sub_status is not None:
                updates.append("sub_status = ?"); params.append(sub_status)
            if last_sub_check is not None:
                updates.append("last_sub_check = ?"); params.append(last_sub_check)
            if local_poster_path is not None:
                updates.append("local_poster_path = ?"); params.append(local_poster_path)
            if task_type is not None:
                updates.append("type = ?"); params.append(task_type)
            if updates:
                params.append(task_id)
                conn.execute(
                    f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
                )
                conn.commit()

        # 归档触发（锁外执行，archive_task 内部有自己的锁）
        if status == "archived":
            _ar = archive_repo or self._archive_repo
            if _ar is not None:
                _ar.archive_task(task_id)
            else:
                logger.warning(
                    f"[TaskRepo] update_task_status: status=archived 但 archive_repo 未注入，"
                    f"task_id={task_id} 跳过归档。请检查 DatabaseManager 初始化顺序。"
                )

    def update_task_sub_status(self, task_id: int, sub_status: str):
        """快速更新任务字幕状态"""
        with self.db_lock:
            conn = self._get_conn()
            conn.execute("UPDATE tasks SET sub_status = ? WHERE id = ?", (sub_status, task_id))
            conn.commit()

    def update_task_is_active(self, task_id: int, is_active: int):
        """快速更新任务激活标志（热表 tasks 专用）"""
        with self.db_lock:
            conn = self._get_conn()
            conn.execute("UPDATE tasks SET is_active = ? WHERE id = ?", (int(is_active), task_id))
            conn.commit()

    def update_any_task_metadata(
        self,
        task_id: int,
        is_archive: bool,
        imdb_id: Optional[str] = None,
        tmdb_id: Optional[str] = None,
        sub_status: Optional[str] = None,
        title: Optional[str] = None,
        year: Optional[str] = None,
        local_poster_path: Optional[str] = None,   # 新增：海报本地路径
        target_path: Optional[str] = None,         # 新增：视频物理路径（重命名后同步）
        clean_name: Optional[str] = None,          # 新增：前端首行显示名（TMDB 译名）
        season: Optional[int] = None,              # 新增：季数（TV）
        episode: Optional[int] = None,             # 新增：集数（TV）
    ) -> None:
        """
        通用双表元数据更新（根据 is_archive 决定写热表还是冷表）
        
        ── 业务链路 ──
        1. 根据 is_archive 标志选择目标表（热表 tasks 或冷表 media_archive）-> 
        2. 构建动态 UPDATE 语句（仅更新非 None 字段）-> 
        3. 执行原子级 UPDATE 并提交事务 -> 
        4. 记录更新结果或异常
        
        ⚠️ ARCHITECT WARNING: 当前采用 is not None 过滤，意味着传入 None 会被跳过，
        无法实现 DB 字段的 NULL 清空。未来若需擦除数据，必须重构为字典传入模式。
        """
        with self.db_lock:
            conn = self._get_conn()
            updates = []
            params = []
            
            # ── 动态构建 UPDATE 字段列表 ──
            # 1. 遍历所有可选参数 -> 2. 若非 None 则添加到 updates 列表 -> 3. 参数值追加到 params
            if imdb_id is not None:
                updates.append("imdb_id = ?"); params.append(imdb_id)
            if tmdb_id is not None:
                updates.append("tmdb_id = ?"); params.append(tmdb_id)
            if sub_status is not None:
                updates.append("sub_status = ?"); params.append(sub_status)
            if title is not None:
                updates.append("title = ?"); params.append(title)
            if year is not None:
                updates.append("year = ?"); params.append(year)
            if local_poster_path is not None:
                updates.append("local_poster_path = ?"); params.append(local_poster_path)
            if target_path is not None:
                updates.append("target_path = ?"); params.append(target_path)
            if clean_name is not None:
                updates.append("clean_name = ?"); params.append(clean_name)
            if season is not None:
                updates.append("season = ?"); params.append(season)
            if episode is not None:
                updates.append("episode = ?"); params.append(episode)
            
            # ── 若无任何字段需更新，直接返回 ──
            if not updates:
                return

            params.append(task_id)

            # ── 根据 is_archive 选择目标表和主键字段 ──
            # 1. is_archive=True：冷表 media_archive，主键为 original_task_id（全局唯一身份证）
            # 2. is_archive=False：热表 tasks，主键为 id
            # 注意：冷表的 original_task_id 已在 get_archived_data 中映射为 "id" 字段返回前端，链路完全闭环
            if is_archive:
                # ✅ 冷表用 original_task_id 匹配（全局唯一身份证，与 get_archived_data 返回的 "id" 保持一致）
                # get_archived_data 已将 original_task_id 映射为 "id" 字段返回前端，链路完全闭环
                table = "media_archive"
                pk_field = "original_task_id"
            else:
                table = "tasks"
                pk_field = "id"

            # ── 执行原子级 UPDATE 并提交事务 ──
            # 1. 构建 SQL 语句 -> 2. 执行查询 -> 3. 提交事务 -> 4. 检查受影响行数 -> 5. 异常时回滚
            try:
                cur = conn.execute(f"UPDATE {table} SET {', '.join(updates)} WHERE {pk_field} = ?", params)
                conn.commit()
                if cur.rowcount == 0:
                    logger.warning(f"[TaskRepo] ⚠️ update_any_task_metadata 零更新: table={table}, {pk_field}={task_id}")
                else:
                    logger.debug(f"[TaskRepo] update_any_task_metadata: table={table}, {pk_field}={task_id}, updates={updates}")
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] update_any_task_metadata 失败: {e}", exc_info=True)
                raise

    def update_task_title_year(
        self,
        task_id: int,
        title: Optional[str] = None,
        year: Optional[str] = None,
        season: Optional[int] = None
    ):
        """更新任务标题、年份和季号"""
        with self.db_lock:
            conn = self._get_conn()
            updates = []
            params = []
            if title is not None:
                updates.append("title = ?"); params.append(title)
            if year is not None:
                updates.append("year = ?"); params.append(year)
            if season is not None:
                updates.append("season = ?"); params.append(season)
            if updates:
                params.append(task_id)
                conn.execute(
                    f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
                )
                conn.commit()

    def reset_orphan_pending_tasks(self) -> int:
        """
        启动时清理孤儿任务：将卡在 pending 超过 2 小时的任务重置为 failed。
        Returns: 重置的孤儿任务数量
        """
        with self.db_lock:
            conn = self._get_conn()
            try:
                cursor = conn.execute(
                    """
                    UPDATE tasks SET status = 'failed'
                    WHERE status = 'pending'
                      AND created_at IS NOT NULL
                      AND (strftime('%s', 'now') - strftime('%s', created_at)) > 7200
                    """
                )
                count = cursor.rowcount
                conn.commit()
                return count
            except Exception as e:
                logger.warning(f"[TaskRepo] reset_orphan_pending_tasks 失败: {e}")
                return 0

    def mark_task_as_ignored_and_inherit(
        self,
        task_id: int,
        is_archive: bool,
        imdb_id: Optional[str] = None,
        tmdb_id: Optional[str] = None
    ) -> bool:
        """
        🚨 架构级原子操作：标记任务为 ignored 并继承同源海报路径
        
        ── 业务链路 ──
        1. 跨表检索同源海报路径（冷表 → 热表）-> 
        2. 原子写入：一次性更新 status + local_poster_path + imdb_id + tmdb_id -> 
        3. 提交事务 -> 4. 返回操作结果
        
        触发场景：文件被 IMDb 重复检测判定为物理副本（PT 做种重复文件）
        
        执行流程（必须原子）：
        1. 跨表检索：从 media_archive/tasks 检索同源海报路径
        2. 状态原子写入：一次性写入 ignored + local_poster_path + imdb_id + tmdb_id
        3. 视觉防护：确保前端获得海报路径，正确触发 VHS TAPE ERROR 特效
        
        Args:
            task_id: 任务 ID
            is_archive: True=冷表，False=热表
            imdb_id: IMDb ID（用于查找同源文件）
            tmdb_id: TMDB ID
        
        Returns:
            bool: 是否成功标记
        """
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                
                # ── Step 1: 跨表检索同源海报路径 ──
                # 业务链路：1. 若有 imdb_id，先从冷表查找同源文件 -> 2. 若冷表无结果，从热表查找 -> 3. 返回海报路径
                inherited_poster = None
                if imdb_id:
                    # 1. 从 media_archive 冷表查找同源文件的海报路径
                    cursor = conn.execute(
                        "SELECT local_poster_path FROM media_archive WHERE imdb_id = ? AND local_poster_path IS NOT NULL LIMIT 1",
                        (imdb_id,)
                    )
                    row = cursor.fetchone()
                    inherited_poster = row[0] if row else None
                    
                    # 2. 如果冷表没找到，从热表 tasks 查找
                    if not inherited_poster:
                        cursor = conn.execute(
                            "SELECT local_poster_path FROM tasks WHERE imdb_id = ? AND local_poster_path IS NOT NULL LIMIT 1",
                            (imdb_id,)
                        )
                        row = cursor.fetchone()
                        inherited_poster = row[0] if row else None
                
                # ── Step 2: 原子写入 ──
                # 业务链路：1. 根据 is_archive 选择目标表 -> 2. 构建动态 UPDATE 语句 -> 3. 一次性提交所有更新
                table = "media_archive" if is_archive else "tasks"
                pk_field = "original_task_id" if is_archive else "id"
                
                # 1. 初始化 UPDATE 字段列表（必须包含 status='ignored'）
                updates = ["status = 'ignored'"]
                params = []
                
                # 2. 若有继承的海报路径，添加到 UPDATE 列表
                if inherited_poster:
                    updates.append("local_poster_path = ?")
                    params.append(inherited_poster)
                
                # 3. 若有 imdb_id，添加到 UPDATE 列表
                if imdb_id:
                    updates.append("imdb_id = ?")
                    params.append(imdb_id)
                
                # 4. 若有 tmdb_id，添加到 UPDATE 列表
                if tmdb_id:
                    updates.append("tmdb_id = ?")
                    params.append(tmdb_id)
                
                params.append(task_id)
                
                # 5. 执行原子级 UPDATE
                cursor = conn.execute(
                    f"UPDATE {table} SET {', '.join(updates)} WHERE {pk_field} = ?",
                    params
                )
                
                # ── Step 3: 提交事务 ──
                conn.commit()
                logger.info(
                    f"[TaskRepo] 🚨 原子操作：标记任务 {task_id} 为 ignored，"
                    f"继承海报: {inherited_poster}, imdb_id: {imdb_id}"
                )
                # ── Step 4: 返回操作结果 ──
                return cursor.rowcount > 0
                
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] 原子操作失败: {e}", exc_info=True)
                raise

    # ==========================================
    # 任务删除
    # ==========================================

    def delete_tasks_and_archive_by_ids(self, ids: List[int]) -> int:
        """
        批量删除任务（同时删除 tasks 和 media_archive 两表）
        
        删除策略：
        1. 从 tasks 表删除指定 ID 的记录
        2. 根据 path 从 media_archive 表删除对应的归档记录
        3. 根据 original_task_id 从 media_archive 表删除对应的归档记录
        
        事务保护：
        - 使用 BEGIN...COMMIT 保证原子性
        - 失败时自动回滚，防止数据不一致
        
        返回：
            int: 删除的总记录数（tasks + archive）
        """
        if not ids:
            return 0
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                placeholders = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"SELECT path FROM tasks WHERE id IN ({placeholders})", ids
                ).fetchall()
                paths = [r[0] for r in rows if r[0]]
                cursor = conn.execute(
                    f"DELETE FROM tasks WHERE id IN ({placeholders})", ids
                )
                tasks_deleted = cursor.rowcount
                archive_deleted = 0
                if paths:
                    pp = ",".join("?" * len(paths))
                    cursor = conn.execute(
                        f"DELETE FROM media_archive WHERE path IN ({pp})", paths
                    )
                    archive_deleted += cursor.rowcount
                cursor = conn.execute(
                    f"DELETE FROM media_archive WHERE original_task_id IN ({placeholders})", ids
                )
                archive_deleted += cursor.rowcount
                conn.commit()
                logger.info(f"[TaskRepo] 批量删除: tasks={tasks_deleted}, archive={archive_deleted}")
                return tasks_deleted + archive_deleted
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] 批量删除失败: {e}")
                raise

    def delete_task_and_archive_by_id(self, task_id: int) -> bool:
        """单条删除任务（同时删除 tasks 和 media_archive 两表）"""
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                row = conn.execute(
                    "SELECT path FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                path = row[0] if row else None
                cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                tasks_deleted = cursor.rowcount
                archive_deleted = 0
                if path:
                    cursor = conn.execute(
                        "DELETE FROM media_archive WHERE path = ?", (path,)
                    )
                    archive_deleted += cursor.rowcount
                cursor = conn.execute(
                    "DELETE FROM media_archive WHERE original_task_id = ?", (task_id,)
                )
                archive_deleted += cursor.rowcount
                conn.commit()
                if tasks_deleted > 0 or archive_deleted > 0:
                    logger.info(f"[TaskRepo] 删除任务 {task_id}: tasks={tasks_deleted}, archive={archive_deleted}")
                    return True
                return False
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] 删除任务 {task_id} 失败: {e}")
                raise

    def delete_tasks_by_ids(self, ids: List[int]):
        """批量删除任务记录（同时清理 media_archive，事务保护防孤儿记录）"""
        if not ids:
            return
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                placeholders = ",".join(["?"] * len(ids))
                rows = conn.execute(
                    f"SELECT path FROM tasks WHERE id IN ({placeholders})", ids
                ).fetchall()
                paths = [r[0] for r in rows if r[0]]
                conn.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids)
                if paths:
                    pp = ",".join(["?"] * len(paths))
                    conn.execute(f"DELETE FROM media_archive WHERE path IN ({pp})", paths)
                conn.execute(
                    f"DELETE FROM media_archive WHERE original_task_id IN ({placeholders})", ids
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] delete_tasks_by_ids 失败，已回滚: {e}")
                raise

    def delete_task(self, task_id: int) -> bool:
        """删除单条任务记录（同时清理 media_archive，事务保护防孤儿记录）"""
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                row = conn.execute(
                    "SELECT path FROM tasks WHERE id = ?", (task_id,)
                ).fetchone()
                path = row[0] if row else None
                cur1 = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                cur2_count = 0
                if path:
                    cur2 = conn.execute("DELETE FROM media_archive WHERE path = ?", (path,))
                    cur2_count = cur2.rowcount
                cur3 = conn.execute(
                    "DELETE FROM media_archive WHERE original_task_id = ?", (task_id,)
                )
                conn.commit()
                return (cur1.rowcount + cur2_count + cur3.rowcount) > 0
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] delete_task {task_id} 失败，已回滚: {e}")
                raise

    def clear_all_tasks(self) -> int:
        """
        清空所有任务记录（核弹按钮 🔴）
        
        危险操作：
        - 同时清空 tasks 和 media_archive 两张表
        - 重置自增 ID 计数器（sqlite_sequence）
        - 不可恢复，请谨慎使用
        
        使用场景：
        - 系统重置
        - 测试环境清理
        - 数据库损坏后重建
        
        事务保护：
        - 使用 BEGIN...COMMIT 保证原子性
        - 失败时自动回滚
        
        返回：
            int: 删除的总记录数
        """
        with self.db_lock:
            conn = self._get_conn()
            try:
                conn.execute("BEGIN")
                cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                count_tasks = cursor.fetchone()[0]
                cursor = conn.execute("SELECT COUNT(*) FROM media_archive")
                count_archive = cursor.fetchone()[0]
                count = count_tasks + count_archive
                conn.execute("DELETE FROM tasks")
                conn.execute("DELETE FROM media_archive")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='tasks'")
                conn.execute("DELETE FROM sqlite_sequence WHERE name='media_archive'")
                conn.commit()
                logger.info(f"[TaskRepo] 已清空任务表，删除 {count} 条记录，自增 ID 已重置")
                return count
            except Exception as e:
                conn.rollback()
                logger.error(f"[TaskRepo] clear_all_tasks 失败，已回滚: {e}")
                raise
