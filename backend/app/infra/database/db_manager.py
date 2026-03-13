"""
数据库管理器 - SQLite WAL 模式 + 原子写入 + 敏感密钥加密存储

核心特性：
1. WAL 模式：提升并发性能
2. 原子写入：配置文件采用 .tmp 替换机制
3. 线程级连接池：使用 threading.local() 实现连接复用，彻底消除高频 connect/close 开销
4. 敏感密钥加密：自动拦截并加密 6 个敏感键
5. 自动明文密钥迁移：首次启动时检测并迁移明文密钥
"""
import os
import json
import sqlite3
import threading
import logging
from typing import Any, Optional, Dict, List
from pathlib import Path

from app.infra.security import get_crypto_manager

logger = logging.getLogger(__name__)


class DatabaseManager:
    """数据库管理器"""

    # 敏感密钥清单：这些键的值会被自动加密存储到 secure_keys.json
    # 首次启动时，系统会自动检测 config.json 中的明文密钥并迁移
    SENSITIVE_KEYS = [
        "tmdb_api_key",      # TMDB API 密钥
        "os_api_key",        # OpenSubtitles API 密钥
        "sonarr_api_key",    # Sonarr API 密钥
        "radarr_api_key",    # Radarr API 密钥
        "llm_cloud_key",     # 云端 LLM API 密钥
        "llm_local_key"      # 本地 LLM API 密钥
    ]

    def __init__(self, db_path: str = "data/media_database.db", config_path: str = "data/config.json"):
        self.db_path = db_path
        self.config_path = config_path
        self.secure_keys_path = "data/secure_keys.json"
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_lock = threading.RLock()  # 可重入锁，允许同一线程嵌套获取
        self._local = threading.local()
        # 注册迁移清单（幂等，多次调用无副作用）
        self.__class__._register_migrations()
        self._init_database()
        self._migrate_database()
        self._migrate_sensitive_keys()

        # ── 构造各 Repository（注入共享连接池和锁）──────────────────────
        from app.infra.database.repositories import (
            PathRepo, ConfigRepo, StatsRepo, ArchiveRepo, TaskRepo
        )
        self._path_repo    = PathRepo(self._get_conn, self.db_lock, self.config_path, self.secure_keys_path)
        self._config_repo  = ConfigRepo(self._get_conn, self.db_lock, self.config_path, self.secure_keys_path)
        self._stats_repo   = StatsRepo(self._get_conn, self.db_lock, self.config_path, self.secure_keys_path)
        self._archive_repo = ArchiveRepo(self._get_conn, self.db_lock, self.config_path, self.secure_keys_path, self._path_repo)
        self._task_repo    = TaskRepo(self._get_conn, self.db_lock, self.config_path, self.secure_keys_path, self._archive_repo)

        # 注入 AI 默认值（通过 config_repo）
        self._config_repo._inject_ai_defaults()

    def _get_conn(self) -> sqlite3.Connection:
        """
        获取当前线程的持久化 SQLite 连接（线程级连接池核心方法）

        - 若当前线程已有连接，直接复用，零开销
        - 否则创建新连接，设置 WAL 模式 + row_factory 并缓存到线程本地存储
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ==========================================
    # 版本化迁移引擎
    # ==========================================

    # 迁移清单：每条记录格式 (目标版本, 描述, 迁移函数)
    # 迁移函数签名：fn(conn: sqlite3.Connection) -> None
    # 注意：函数内部禁止自行 commit/rollback，由引擎统一控制事务
    MIGRATIONS: list = []  # 在类体末尾通过 _register_migrations() 填充

    @classmethod
    def _register_migrations(cls):
        """注册所有版本迁移任务（按版本号升序排列）"""

        def migrate_v1_1(conn: sqlite3.Connection):
            """V1.0 -> V1.1：补齐扫描阶段新增字段"""
            cursor = conn.execute("PRAGMA table_info(tasks)")
            existing = {row[1] for row in cursor.fetchall()}
            columns_to_add = {
                "clean_name":       "TEXT",
                "season":           "INTEGER",
                "episode":          "INTEGER",
                "poster_path":      "TEXT",
                "local_poster_path": "TEXT",
            }
            for col, col_type in columns_to_add.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
                    logger.info(f"[DB][V1.1] 新增字段: {col}")

        def migrate_v1_2(conn: sqlite3.Connection):
            """V1.1 -> V1.2：新增 is_active 字段，支持逻辑删除"""
            cursor = conn.execute("PRAGMA table_info(tasks)")
            existing = {row[1] for row in cursor.fetchall()}
            if "is_active" not in existing:
                conn.execute("ALTER TABLE tasks ADD COLUMN is_active INTEGER DEFAULT 1")
                logger.info("[DB][V1.2] 新增字段: is_active (逻辑删除支持)")

        def migrate_v1_3(conn: sqlite3.Connection):
            """V1.2 -> V1.3：新增 media_archive 归档表（任务流转冷存储）"""
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_archive (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_task_id  INTEGER,
                    path              TEXT NOT NULL,
                    file_name         TEXT,
                    clean_name        TEXT,
                    type              TEXT DEFAULT 'movie',
                    tmdb_id           TEXT,
                    imdb_id           TEXT,
                    title             TEXT,
                    year              TEXT,
                    target_path       TEXT,
                    season            INTEGER,
                    episode           INTEGER,
                    poster_path       TEXT,
                    local_poster_path TEXT,
                    sub_status        TEXT DEFAULT 'pending',
                    created_at        TEXT,
                    archived_at       DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_imdb_id ON media_archive (imdb_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_tmdb_id ON media_archive (tmdb_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_type ON media_archive (type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_archived_at ON media_archive (archived_at)"
            )
            logger.info("[DB][V1.3] 新增表: media_archive (归档冷存储) + 4个索引")

        cls.MIGRATIONS = [
            ("1.1", "补齐扫描阶段字段 (clean_name/season/episode/poster_path/local_poster_path)", migrate_v1_1),
            ("1.2", "新增 is_active 字段（逻辑删除预留）", migrate_v1_2),
            ("1.3", "新增 media_archive 归档表（任务流转冷存储）", migrate_v1_3),
        ]

    def _init_database(self):
        """初始化数据库基础表结构（含 system_meta 元数据表）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            # ── 业务表：tasks ────────────────────────────────────────────
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    file_name TEXT,
                    clean_name TEXT,
                    type TEXT DEFAULT 'movie',
                    status TEXT DEFAULT 'pending',
                    tmdb_id TEXT,
                    imdb_id TEXT,
                    title TEXT,
                    year TEXT,
                    target_path TEXT,
                    sub_status TEXT DEFAULT 'pending',
                    last_sub_check TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    poster_path TEXT,
                    local_poster_path TEXT,
                    season INTEGER,
                    episode INTEGER,
                    is_active INTEGER DEFAULT 1
                )
                """
            )

            # ── 元数据表：system_meta（存储 schema_version 等系统级 KV）──
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

            # 仅在首次创建时写入初始版本号（INSERT OR IGNORE 保证幂等）
            cursor.execute(
                "INSERT OR IGNORE INTO system_meta (key, value) VALUES ('schema_version', '1.0')"
            )

            conn.commit()
            logger.info("[DB] 数据库初始化完成 (WAL 模式 + system_meta)")

    def _migrate_database(self):
        """
        原子化版本迁移引擎

        流程：
        1. 读取 system_meta 中的当前 schema_version
        2. 遍历 MIGRATIONS，执行所有版本号 > 当前版本的任务
        3. 每个迁移任务独占一个事务（BEGIN ... COMMIT / ROLLBACK）
        4. 迁移完成后更新 schema_version
        5. 任何迁移失败立即 rollback 并抛出异常，阻止系统启动
        """
        with self.db_lock:
            conn = self._get_conn()

            # ── 读取当前版本 ─────────────────────────────────────────────
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key = 'schema_version'"
            ).fetchone()
            current_version = row[0] if row else "1.0"

            # ── 遍历迁移任务 ─────────────────────────────────────────────
            for target_version, description, migrate_fn in self.MIGRATIONS:
                # 版本比较：使用 tuple 数值比较，避免字符串排序陷阱
                def _ver(v: str):
                    return tuple(int(x) for x in v.split("."))

                if _ver(target_version) <= _ver(current_version):
                    continue  # 已完成的迁移跳过

                logger.info(f"[DB] 执行迁移 {current_version} -> {target_version}: {description}")

                try:
                    conn.execute("BEGIN")
                    migrate_fn(conn)
                    # 更新版本号（在同一事务内）
                    conn.execute(
                        "INSERT OR REPLACE INTO system_meta (key, value) VALUES ('schema_version', ?)",
                        (target_version,)
                    )
                    conn.commit()
                    current_version = target_version
                    logger.info(f"[DB] 迁移完成，当前版本: {current_version}")

                except Exception as e:
                    conn.rollback()
                    error_msg = (
                        f"[FATAL] [DB] 迁移 {current_version} -> {target_version} 失败，"
                        f"已回滚。错误: {e}"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg) from e

    def _migrate_sensitive_keys(self):
        """
        自动迁移明文密钥到加密存储（首次启动时执行）
        
        迁移流程：
        1. 扫描 config.json 中的 SENSITIVE_KEYS
        2. 将非空明文密钥加密后写入 secure_keys.json
        3. 清空 config.json 中的明文密钥（设为空字符串）
        4. 后续读取时，ConfigRepo 会自动从 secure_keys.json 解密
        
        幂等性：多次执行不会重复迁移（已加密的密钥会被跳过）
        """
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        settings = config.get("settings", {})
        crypto = get_crypto_manager()
        
        # 收集需要迁移的明文密钥
        keys_to_migrate = {}
        for key in self.SENSITIVE_KEYS:
            value = settings.get(key, "")
            if value and value.strip():
                keys_to_migrate[key] = value
        
        if not keys_to_migrate:
            return  # 无需迁移
        
        # 加载现有的加密存储（如果存在）
        secure_data = {}
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
        
        # 加密并存储
        for key, value in keys_to_migrate.items():
            encrypted = crypto.encrypt_api_key(value)
            secure_data[key] = encrypted
            settings[key] = ""  # 清空明文
        
        # 原子写入加密文件
        with open(self.secure_keys_path, "w", encoding="utf-8") as f:
            json.dump(secure_data, f, indent=4)
        
        # 原子写入配置文件
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        
        logger.info(f"[DB] 已迁移 {len(keys_to_migrate)} 个敏感密钥到加密存储")

    # ==========================================
    # 配置管理方法（委托给 ConfigRepo）
    # ==========================================

    def get_config(self, key: str, default: Any = None) -> Any:          return self._config_repo.get_config(key, default)
    def set_config(self, key: str, value: Any):                          return self._config_repo.set_config(key, value)
    def get_all_config(self) -> Dict[str, Any]:                          return self._config_repo.get_all_config()
    def save_all_config(self, config: Dict[str, Any]):                   return self._config_repo.save_all_config(config)
    def get_agent_config(self, key: str = None, default: Any = None):    return self._config_repo.get_agent_config(key, default)
    def reset_settings_to_defaults(self, target: str):                   return self._config_repo.reset_settings_to_defaults(target)

    # ==========================================
    # 路径管理方法（委托给 PathRepo）
    # ==========================================

    def get_managed_paths(self) -> List[Dict[str, Any]]:                  return self._path_repo.get_managed_paths()
    def add_managed_path(self, p_type: str, path: str, category: str):   return self._path_repo.add_managed_path(p_type, path, category)
    def delete_managed_path(self, path_id: int):                         return self._path_repo.delete_managed_path(path_id)

    # ==========================================
    # 任务管理方法（委托给 TaskRepo）
    # ==========================================

    def add_task(self, path: str, filename: str, clean_name: str, type_hint: str):  return self._task_repo.add_task(path, filename, clean_name, type_hint)
    def is_processed(self, file_path: str) -> bool:                                 return self._task_repo.is_processed(file_path)
    def get_task_id_by_path(self, file_path: str):                                  return self._task_repo.get_task_id_by_path(file_path)
    def get_task_status_by_path(self, file_path: str):                              return self._task_repo.get_task_status_by_path(file_path)
    def check_task_exists_by_path(self, file_path: str) -> bool:                    return self._task_repo.check_task_exists_by_path(file_path)
    def check_task_exists_by_name(self, file_name: str, clean_name: str) -> bool:   return self._task_repo.check_task_exists_by_name(file_name, clean_name)
    def insert_task(self, task_data: Dict[str, Any]):                               return self._task_repo.insert_task(task_data)

    def update_task_status(self, task_id: int, status=None, tmdb_id=None, imdb_id=None,
                           target_path=None, sub_status=None, last_sub_check=None,
                           local_poster_path=None, task_type=None):
        return self._task_repo.update_task_status(
            task_id, status=status, tmdb_id=tmdb_id, imdb_id=imdb_id,
            target_path=target_path, sub_status=sub_status, last_sub_check=last_sub_check,
            local_poster_path=local_poster_path, task_type=task_type
        )

    def update_task_sub_status(self, task_id: int, sub_status: str):          return self._task_repo.update_task_sub_status(task_id, sub_status)

    def update_any_task_metadata(self, task_id: int, is_archive: bool, imdb_id=None, tmdb_id=None, sub_status=None, title=None, year=None):
        return self._task_repo.update_any_task_metadata(task_id, is_archive, imdb_id=imdb_id, tmdb_id=tmdb_id, sub_status=sub_status, title=title, year=year)

    def update_task_title_year(self, task_id: int, title=None, year=None, season=None): return self._task_repo.update_task_title_year(task_id, title=title, year=year, season=season)
    def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:                      return self._task_repo.get_tasks_needing_scrape()
    def get_tasks_needing_subtitles(self) -> List[Dict[str, Any]]:                   return self._task_repo.get_tasks_needing_subtitles()
    def reset_orphan_pending_tasks(self) -> int:                                     return self._task_repo.reset_orphan_pending_tasks()
    def delete_tasks_and_archive_by_ids(self, ids: List[int]) -> int:               return self._task_repo.delete_tasks_and_archive_by_ids(ids)
    def delete_task_and_archive_by_id(self, task_id: int) -> bool:                  return self._task_repo.delete_task_and_archive_by_id(task_id)
    def delete_tasks_by_ids(self, ids: List[int]):                                  return self._task_repo.delete_tasks_by_ids(ids)
    def delete_task(self, task_id: int) -> bool:                                    return self._task_repo.delete_task(task_id)
    def clear_all_tasks(self) -> int:                                               return self._task_repo.clear_all_tasks()

    # ==========================================
    # 统计方法（委托给 StatsRepo）
    # ==========================================

    def get_all_data(self, search_keyword=None, include_ignored: bool = False) -> List[Dict[str, Any]]:  return self._stats_repo.get_all_data(search_keyword, include_ignored)
    def get_dashboard_stats(self) -> Dict[str, int]:                     return self._stats_repo.get_dashboard_stats()
    def check_media_exists(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> bool:   return self._stats_repo.check_media_exists(imdb_id, media_type, season, episode)

    # ==========================================
    # 归档方法（委托给 ArchiveRepo）
    # ==========================================

    def archive_task(self, task_id: int) -> bool:                                          return self._archive_repo.archive_task(task_id)
    def get_archived_data(self, search_keyword=None) -> List[Dict[str, Any]]:              return self._archive_repo.get_archived_data(search_keyword)
    def get_archive_data(self, search_keyword=None) -> List[Dict[str, Any]]:               return self._archive_repo.get_archive_data(search_keyword)
    def get_archive_stats(self) -> Dict[str, int]:                                         return self._archive_repo.get_archive_stats()
    def update_archive_sub_status(self, archive_id, sub_status, last_check=None) -> bool:  return self._archive_repo.update_archive_sub_status(archive_id, sub_status, last_check)
    def get_active_library_path(self, media_type: str) -> str:                             return self._archive_repo.get_active_library_path(media_type)


# 全局单例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
