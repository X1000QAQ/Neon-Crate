"""
stats_repo.py - 统计仓储

职责：提供仪表盘和媒体库的统计数据查询，全部为只读操作，零副作用。

迁入方法（原 db_manager.py）：
  - get_dashboard_stats   (原行 625)
  - get_all_data          (原行 561)
  - check_imdb_id_exists  (原行 613)

Impact 分析（2026-03-12）：
  get_dashboard_stats  → HIGH  (1 direct: get_stats, 4 processes)
  get_all_data         → CRITICAL (3 direct: _generate_llm_response/_get_system_stats/get_all_tasks, 10 processes)
  check_imdb_id_exists → LOW  (0 direct callers)
  迁移安全：外观层接口不变，所有调用方零感知。

依赖：_get_conn()、db_lock（均通过 BaseRepository 注入）
"""
from typing import Any, Dict, List, Optional

from .base import BaseRepository


class StatsRepo(BaseRepository):
    """统计仓储：提供仪表盘和媒体库统计数据，只读操作"""

    def get_dashboard_stats(self) -> Dict[str, int]:
        """获取仪表盘统计数据（movies/tv_shows/pending/completed）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE type = 'movie' AND status != 'failed'")
            movies = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE type = 'tv' AND status != 'failed'")
            tv_shows = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE target_path IS NOT NULL AND target_path != ''")
            completed = cursor.fetchone()[0]
            return {"movies": movies, "tv_shows": tv_shows, "pending": pending, "completed": completed}

    def get_all_data(self, search_keyword: Optional[str] = None, include_ignored: bool = False) -> List[Dict[str, Any]]:
        """获取所有任务数据（含搜索过滤）。默认隐藏 ignored 记录，需显式传 include_ignored=True 才返回。"""
        with self.db_lock:
            conn = self._get_conn()
            ignored_clause = "" if include_ignored else " AND status != 'ignored'"
            
            # 🚀 双表联合查询：统一使用 original_task_id 作为冷表的对外 ID
            base_query = f"""
                SELECT id, path, file_name, clean_name, type, status, tmdb_id, imdb_id, title, year, 
                       target_path, sub_status, last_sub_check, created_at, poster_path, local_poster_path, 
                       season, episode 
                FROM tasks 
                WHERE 1=1 {ignored_clause}
                UNION ALL
                SELECT original_task_id as id, path, file_name, clean_name, type, 'archived' as status, 
                       tmdb_id, imdb_id, title, year, target_path, sub_status, NULL as last_sub_check, 
                       created_at, poster_path, local_poster_path, season, episode 
                FROM media_archive
                WHERE 1=1
            """
            
            if search_keyword:
                cursor = conn.execute(
                    f"WITH combined AS ({base_query}) SELECT * FROM combined WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ? ORDER BY created_at DESC",
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(f"WITH combined AS ({base_query}) SELECT * FROM combined ORDER BY created_at DESC")
            
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3],
                    "type": r[4], "status": r[5], "tmdb_id": r[6], "imdb_id": r[7],
                    "title": r[8], "year": r[9], "target_path": r[10],
                    "sub_status": r[11], "last_sub_check": r[12], "created_at": r[13],
                    "poster_path": r[14], "local_poster_path": r[15],
                    "season": r[16], "episode": r[17]
                }
                for r in rows
            ]

    def check_media_exists(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> bool:
        """检查媒体是否已存在（精确到季集，彻底解决剧集共享 IMDb ID 被连坐误杀问题）"""
        if not imdb_id or not str(imdb_id).strip():
            return False
        _imdb = str(imdb_id).strip()
        with self.db_lock:
            conn = self._get_conn()
            if media_type == "movie":
                # 电影：仅查 IMDb ID + type
                if conn.execute(
                    "SELECT 1 FROM media_archive WHERE imdb_id = ? AND type = 'movie' LIMIT 1",
                    (_imdb,)
                ).fetchone():
                    return True
                if conn.execute(
                    "SELECT 1 FROM tasks WHERE imdb_id = ? AND type = 'movie' AND status IN ('archived', 'scraped') LIMIT 1",
                    (_imdb,)
                ).fetchone():
                    return True
            elif media_type == "tv":
                # 剧集：必须精确到 season + episode，防止同剧不同集被误杀
                if season is None or episode is None:
                    return False
                if conn.execute(
                    "SELECT 1 FROM media_archive WHERE imdb_id = ? AND type = 'tv' AND season = ? AND episode = ? LIMIT 1",
                    (_imdb, season, episode)
                ).fetchone():
                    return True
                if conn.execute(
                    "SELECT 1 FROM tasks WHERE imdb_id = ? AND type = 'tv' AND season = ? AND episode = ? AND status IN ('archived', 'scraped') LIMIT 1",
                    (_imdb, season, episode)
                ).fetchone():
                    return True
            return False
