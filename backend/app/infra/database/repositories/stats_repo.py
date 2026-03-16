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
        """
        获取所有任务数据（含搜索过滤）。默认隐藏 ignored 记录，需显式传 include_ignored=True 才返回。
        
        ── 业务链路 ──
        1. 构建双表 UNION ALL 查询（热表 tasks + 冷表 media_archive）-> 
        2. 统一使用 original_task_id 作为冷表的对外 ID -> 
        3. 应用搜索过滤（可选）-> 4. 按创建时间倒序排列 -> 
        5. 将查询结果转换为字典列表 -> 6. 返回最终结果
        """
        with self.db_lock:
            conn = self._get_conn()
            # ── Step 1: 构建过滤条件 ──
            # 业务链路：1. 若 include_ignored=False，则添加 status != 'ignored' 过滤 -> 
            # 2. 否则返回所有记录（包括 ignored）
            ignored_clause = "" if include_ignored else " AND status != 'ignored'"
            
            # ── Step 2: 构建双表 UNION ALL 查询 ──
            # 业务链路：1. 查询热表 tasks（所有字段直接返回）-> 
            # 2. 查询冷表 media_archive（将 original_task_id 映射为 id，status 固定为 'archived'）-> 
            # 3. 使用 UNION ALL 合并两个查询结果（保留重复记录，后续去重）
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
            
            # ── Step 3: 应用搜索过滤（可选）──
            # 业务链路：1. 若有搜索关键词，则在 file_name / clean_name / title 中模糊匹配 -> 
            # 2. 使用 WITH 子句包装 UNION ALL 查询 -> 3. 在 WHERE 中应用搜索条件
            if search_keyword:
                cursor = conn.execute(
                    f"WITH combined AS ({base_query}) SELECT * FROM combined WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ? ORDER BY created_at DESC",
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                # ── Step 4: 无搜索条件时直接返回所有记录 ──
                # 业务链路：1. 执行 UNION ALL 查询 -> 2. 按创建时间倒序排列
                cursor = conn.execute(f"WITH combined AS ({base_query}) SELECT * FROM combined ORDER BY created_at DESC")
            
            # ── Step 5: 将查询结果转换为字典列表 ──
            # 业务链路：1. 获取所有行 -> 2. 逐行转换为字典 -> 3. 返回字典列表
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

    def get_sibling_poster(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> Optional[str]:
        """
        根据 IMDb ID（+ 剧集维度）查找已归档的同源任务，返回其 local_poster_path。
        用于 ignored 任务继承同源海报，保证前端视觉效果正常。
        优先查 media_archive（已归档冷表），再查 tasks 热表。
        """
        if not imdb_id or not str(imdb_id).strip():
            return None
        _imdb = str(imdb_id).strip()
        with self.db_lock:
            conn = self._get_conn()
            if media_type == "movie":
                # 电影：按 imdb_id 查，优先取有海报的记录
                row = conn.execute(
                    "SELECT local_poster_path FROM media_archive WHERE imdb_id = ? AND type = 'movie' AND local_poster_path IS NOT NULL LIMIT 1",
                    (_imdb,)
                ).fetchone()
                if row:
                    return row[0]
                row = conn.execute(
                    "SELECT local_poster_path FROM tasks WHERE imdb_id = ? AND type = 'movie' AND local_poster_path IS NOT NULL LIMIT 1",
                    (_imdb,)
                ).fetchone()
                return row[0] if row else None
            elif media_type == "tv":
                # 剧集：Show 级海报——查同一 imdb_id 的剧集根目录海报
                # 策略：取同 imdb_id 的任意 archived 记录的 local_poster_path（剧集主海报路径相同）
                row = conn.execute(
                    "SELECT local_poster_path FROM media_archive WHERE imdb_id = ? AND type = 'tv' AND local_poster_path IS NOT NULL LIMIT 1",
                    (_imdb,)
                ).fetchone()
                if row:
                    return row[0]
                row = conn.execute(
                    "SELECT local_poster_path FROM tasks WHERE imdb_id = ? AND type = 'tv' AND local_poster_path IS NOT NULL LIMIT 1",
                    (_imdb,)
                ).fetchone()
                return row[0] if row else None
        return None

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
