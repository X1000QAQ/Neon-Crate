"""
archive_repo.py - 归档仓储

职责：管理 media_archive 表，负责任务从热存储（tasks）到冷存储（media_archive）的流转。

迁入方法（原 db_manager.py）：
  - archive_task              (原行 708)
  - get_archived_data         (原行 587)
  - get_archive_data          (原行 758)
  - get_archive_stats         (原行 795)
  - update_archive_sub_status (原行 808)
  - get_active_library_path   (原行 663)

Impact 分析（2026-03-12）：
  archive_task              → CRITICAL (1 direct: update_task_status → scrape + retry 流程)
  get_active_library_path   → HIGH     (1 direct: perform_scrape_all_task_sync)
  update_archive_sub_status → HIGH     (1 direct: download_subtitle_for_task → 字幕流程)
  get_archived_data         → LOW      (图谱无直接调用者)
  get_archive_data          → LOW      (图谱无直接调用者)
  get_archive_stats         → LOW      (图谱无直接调用者)
  迁移安全：外观层接口不变，所有调用方零感知。

跨域依赖：
  get_active_library_path 依赖 get_managed_paths（来自 PathRepo）。
  通过构造注入 path_repo 实例解决，避免循环依赖。

依赖：_get_conn()、db_lock（BaseRepository 注入）、path_repo（构造注入）
"""
import os
import logging
from typing import Any, Dict, List, Optional

from .base import BaseRepository

logger = logging.getLogger(__name__)


class ArchiveRepo(BaseRepository):
    """归档仓储：管理 media_archive 表及任务冷热存储流转"""

    def __init__(self, get_conn_fn, db_lock, config_path: str, secure_keys_path: str, path_repo):
        """
        Args:
            path_repo: PathRepo 实例，用于 get_active_library_path 中的路径查询。
                       通过构造注入避免循环依赖。
        """
        super().__init__(get_conn_fn, db_lock, config_path, secure_keys_path)
        self._path_repo = path_repo

    # ==========================================
    # 归档核心方法
    # ==========================================

    def archive_task(self, task_id: int) -> bool:
        """
        原子事务归档单条任务。
        前置条件：tasks 中对应记录 status 必须为 'archived'。
        操作：将任务完整复制到 media_archive 表，然后物理删除 tasks 中的记录。
        """
        with self.db_lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT id, path, file_name, clean_name, type, tmdb_id, imdb_id,
                       title, year, target_path, season, episode,
                       poster_path, local_poster_path, sub_status, created_at, status
                FROM tasks WHERE id = ? LIMIT 1
                """,
                (task_id,)
            ).fetchone()
            if row is None:
                return False
            # 前置检查：仅归档 status='archived' 的记录
            if row[16] != "archived":
                return False
            try:
                conn.execute("BEGIN")
                conn.execute(
                    """
                    INSERT INTO media_archive (
                        original_task_id, path, file_name, clean_name, type,
                        tmdb_id, imdb_id, title, year, target_path,
                        season, episode, poster_path, local_poster_path,
                        sub_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row[0],  row[1],  row[2],  row[3],  row[4],
                        row[5],  row[6],  row[7],  row[8],  row[9],
                        row[10], row[11], row[12], row[13],
                        row[14], row[15]
                    )
                )
                # 归档完成后物理删除 tasks 中的原始记录
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                logger.info(f"[ArchiveRepo] 任务已归档并从 tasks 移除。task_id={task_id}")
                return True
            except Exception as e:
                conn.rollback()
                logger.error(f"[ArchiveRepo] archive_task 失败，已回滚。task_id={task_id}, 错误: {e}")
                raise

    # ==========================================
    # 归档查询方法
    # ==========================================

    def get_archived_data(self, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取 media_archive 表中的归档数据（媒体墙展示用）

        Bug 2b 修复：SELECT 加入 original_task_id，并映射为 "id" 返回前端。
        前端持有的 task.id 永远是全局唯一身份证（original_task_id），
        update_any_task_metadata(is_archive=True) 用 original_task_id 匹配，链路完全闭环。
        """
        with self.db_lock:
            conn = self._get_conn()
            # r[0]=id(冷表自增), r[1]=original_task_id, r[2]=path, r[3]=file_name
            # r[4]=clean_name, r[5]=type, r[6]=tmdb_id, r[7]=imdb_id, r[8]=title
            # r[9]=year, r[10]=target_path, r[11]=sub_status, r[12]=created_at
            # r[13]=poster_path, r[14]=local_poster_path, r[15]=season, r[16]=episode
            sql_select = (
                "SELECT id, original_task_id, path, file_name, clean_name, type, "
                "tmdb_id, imdb_id, title, year, "
                "target_path, sub_status, created_at, poster_path, local_poster_path, season, episode "
                "FROM media_archive"
            )
            if search_keyword:
                cursor = conn.execute(
                    sql_select + " WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ? ORDER BY archived_at DESC",
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(sql_select + " ORDER BY archived_at DESC")
            rows = cursor.fetchall()
            return [
                {
                    # ✅ "id" 映射为 original_task_id（全局唯一身份证），前端所有增删改查以此为准
                    "id": r[1], "path": r[2], "file_name": r[3], "clean_name": r[4],
                    "type": r[5], "status": "archived", "tmdb_id": r[6], "imdb_id": r[7],
                    "title": r[8], "year": r[9], "target_path": r[10],
                    "sub_status": r[11], "last_sub_check": None, "created_at": r[12],
                    "poster_path": r[13], "local_poster_path": r[14],
                    "season": r[15], "episode": r[16],
                    "media_archive_pk": r[0],   # 冷表自增 PK，仅供调试，业务逻辑勿用
                }
                for r in rows
            ]


    def get_archive_data(self, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询归档历史记录（归档管理页面用）"""
        with self.db_lock:
            conn = self._get_conn()
            if search_keyword:
                cursor = conn.execute(
                    """
                    SELECT id, task_id, path, file_name, clean_name, type,
                           tmdb_id, imdb_id, title, year, target_path,
                           season, episode, archived_at
                    FROM media_archive
                    WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ?
                    ORDER BY archived_at DESC
                    """,
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, original_task_id, path, file_name, clean_name, type,
                           tmdb_id, imdb_id, title, year, target_path,
                           season, episode, archived_at
                    FROM media_archive
                    ORDER BY archived_at DESC
                    """
                )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0], "original_task_id": r[1], "path": r[2], "file_name": r[3],
                    "clean_name": r[4], "type": r[5], "tmdb_id": r[6], "imdb_id": r[7],
                    "title": r[8], "year": r[9], "target_path": r[10],
                    "season": r[11], "episode": r[12], "archived_at": r[13]
                }
                for r in rows
            ]

    def get_archive_stats(self) -> Dict[str, int]:
        """归档统计：返回归档总数、电影数、剧集数"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media_archive")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE type = 'movie'")
            movies = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE type = 'tv'")
            tv_shows = cursor.fetchone()[0]
            return {"total": total, "movies": movies, "tv_shows": tv_shows}

    def update_archive_sub_status(
        self,
        archive_id: int,
        sub_status: str,
        last_check: Optional[str] = None
    ) -> bool:
        """更新归档表中的字幕状态（字幕引擎写回专用）
        
        ⚠️ ID 契约：archive_id 传入的是 original_task_id（前端可见的虚拟 ID），
        非 media_archive 的物理自增 id。WHERE 子句必须使用 original_task_id 匹配。
        """
        with self.db_lock:
            conn = self._get_conn()
            if last_check:
                conn.execute(
                    "UPDATE media_archive SET sub_status = ?, archived_at = ? WHERE original_task_id = ?",
                    (sub_status, last_check, archive_id)
                )
            else:
                conn.execute(
                    "UPDATE media_archive SET sub_status = ? WHERE original_task_id = ?",
                    (sub_status, archive_id)
                )
            conn.commit()
            return True

    # ==========================================
    # 路径相关（跨域：依赖 path_repo）
    # ==========================================

    def get_active_library_path(self, media_type: str) -> str:
        """
        获取活动媒体库路径（1+1 绝对约束）。
        依赖 path_repo.get_managed_paths() 读取路径配置。
        """
        paths = self._path_repo.get_managed_paths()
        active_libs = [
            p for p in paths
            if str(p.get("type", "")).strip().lower() in ["library", "media", "storage"]
            and p.get("enabled", True)
        ]
        movie_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "movie"]
        tv_libs    = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "tv"]

        if len(movie_libs) > 1 or len(tv_libs) > 1:
            raise ValueError("[ERROR] [配置错误] 系统规定同时只能开启 1个电影媒体库 和 1个剧集媒体库！")
        if len(movie_libs) == 0:
            raise ValueError("[ERROR] [配置错误] 缺少处于开启状态的 Movie (电影) 媒体库！")
        if len(tv_libs) == 0:
            raise ValueError("[ERROR] [配置错误] 缺少处于开启状态的 TV (剧集) 媒体库！")

        media_type = str(media_type or "movie").strip().lower()
        if media_type == "movie":
            return os.path.abspath(movie_libs[0].get("path"))
        elif media_type == "tv":
            return os.path.abspath(tv_libs[0].get("path"))
        else:
            raise ValueError(f"未知的媒体类型: {media_type}")
