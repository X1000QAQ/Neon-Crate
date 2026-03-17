"""
数据库管理器 - SQLite WAL 模式 + 原子写入 + 敏感密钥加密存储

核心特性：
1. WAL 模式：提升并发性能
2. 原子写入：配置文件采用 .tmp 替换机制
3. 线程级连接池：使用 threading.local() 实现连接复用，彻底消除高频 connect/close 开销
4. 敏感密钥加密：自动拦截并加密 6 个敏感键
5. 首次启动自动将 config.json 中的明文密钥迁移至 secure_keys.json 加密存储
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
        
        ── 业务链路 ──
        1. 检查当前线程是否已有缓存连接 -> 2. 若有则直接复用（零开销）-> 
        3. 若无则创建新连接 -> 4. 配置 WAL 模式和行工厂 -> 5. 缓存到线程本地存储 -> 6. 返回连接
        
        设计目标：
        - 消除高频 connect/close 开销（每次查询都要建立连接的性能灾难）
        - 线程安全（每个线程独立连接，无竞态条件）
        - 自动连接复用（同一线程的多次查询共享一个连接）
        
        Returns:
            sqlite3.Connection: 当前线程的持久化连接
        """
        # ── Step 1: 检查线程本地存储中是否已有连接 ──
        # 1. 从 threading.local() 中读取 conn 属性 -> 2. 若存在则直接返回（零开销）
        conn = getattr(self._local, "conn", None)
        if conn is None:
            # ── Step 2: 创建新连接 ──
            # 1. 连接到 SQLite 数据库文件 -> 2. 设置 check_same_thread=False（允许跨线程使用，但由 db_lock 保护）
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            # ── Step 3: 配置 WAL 模式 ──
            # 1. 启用 WAL（Write-Ahead Logging）模式 -> 2. 提升并发读写性能（读不阻塞写）
            conn.execute("PRAGMA journal_mode=WAL")
            # ── Step 4: 配置行工厂 ──
            # 1. 设置 row_factory=sqlite3.Row -> 2. 使查询结果可按列名访问（r["column_name"]）
            conn.row_factory = sqlite3.Row
            # ── Step 5: 缓存到线程本地存储 ──
            # 1. 将连接对象存储到 self._local.conn -> 2. 下次同线程调用时直接复用
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
        """
        注册所有版本迁移任务（按版本号升序排列）。
        当前基准线为 v1.0.0，无待注册迁移。
        如需新增字段，在此处追加新版本（>1.0.0）迁移条目即可。
        """
        cls.MIGRATIONS = []

    def _init_database(self):
        """初始化数据库基础表结构（Baseline Version 1.0.0）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            # ── 业务表：tasks（Baseline 1.0.0，含全部历史字段）───────────
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    path              TEXT UNIQUE NOT NULL,
                    file_name         TEXT,
                    clean_name        TEXT,
                    type              TEXT DEFAULT 'movie',
                    status            TEXT DEFAULT 'pending',
                    tmdb_id           TEXT,
                    imdb_id           TEXT,
                    title             TEXT,
                    year              TEXT,
                    target_path       TEXT,
                    sub_status        TEXT DEFAULT 'pending',
                    last_sub_check    TEXT,
                    created_at        TEXT DEFAULT CURRENT_TIMESTAMP,
                    poster_path       TEXT,
                    local_poster_path TEXT,
                    season            INTEGER,
                    episode           INTEGER,
                    is_active         INTEGER DEFAULT 1
                )
                """
            )

            # ── 归档冷存储表：media_archive（Baseline 1.0.0）──────────────
            cursor.execute(
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
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_imdb_id ON media_archive (imdb_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_tmdb_id ON media_archive (tmdb_id)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_type ON media_archive (type)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_archived_at ON media_archive (archived_at)"
            )

            # ── 元数据表：system_meta（存储 schema_version 等系统级 KV）──
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

            # 新安装直接以 1.0.0 为基准线（INSERT OR IGNORE 保证幂等，不覆盖已有版本）
            cursor.execute(
                "INSERT OR IGNORE INTO system_meta (key, value) VALUES ('schema_version', '1.0.0')"
            )

            conn.commit()
            logger.info("[INFO][DB] 数据库初始化完成 (Baseline Version 1.0.0)")

    def _migrate_database(self):
        """
        原子化版本迁移引擎

        ── 业务链路 ──
        1. 读取 system_meta 中的当前 schema_version -> 
        2. 遍历 MIGRATIONS，执行所有版本号 > 当前版本的任务 -> 
        3. 每个迁移任务独占一个事务（BEGIN ... COMMIT / ROLLBACK）-> 
        4. 迁移完成后更新 schema_version -> 
        5. 任何迁移失败立即 rollback 并抛出异常，阻止系统启动
        """
        with self.db_lock:
            conn = self._get_conn()

            # ── Step 1: 读取当前版本 ──
            # 业务链路：1. 查询 system_meta 表中的 schema_version -> 2. 若无记录则默认为 1.0
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key = 'schema_version'"
            ).fetchone()
            current_version = row[0] if row else "1.0"

            # ── Step 2: 遍历迁移任务 ──
            # 业务链路：1. 遍历 MIGRATIONS 列表 -> 2. 版本比较（跳过已完成的迁移）-> 
            # 3. 执行迁移函数 -> 4. 更新版本号 -> 5. 异常处理与回滚
            for target_version, description, migrate_fn in self.MIGRATIONS:
                # ── 版本比较逻辑 ──
                # 业务链路：1. 将版本字符串转换为元组（如 "1.0.1" -> (1, 0, 1)）-> 
                # 2. 使用元组数值比较（避免字符串排序陷阱）
                def _ver(v: str):
                    return tuple(int(x) for x in v.split("."))

                # 1. 若目标版本 <= 当前版本，说明迁移已完成，跳过
                if _ver(target_version) <= _ver(current_version):
                    continue  # 已完成的迁移跳过

                logger.info(f"[DB] 执行迁移 {current_version} -> {target_version}: {description}")

                try:
                    # ── Step 3: 事务开启与迁移执行 ──
                    # 业务链路：1. 开启事务（BEGIN）-> 2. 执行迁移函数 -> 
                    # 3. 在同一事务内更新版本号 -> 4. 提交事务（COMMIT）
                    conn.execute("BEGIN")
                    # 1. 执行迁移函数（由子类实现具体迁移逻辑）
                    migrate_fn(conn)
                    # 2. 更新版本号（在同一事务内，确保原子性）
                    conn.execute(
                        "INSERT OR REPLACE INTO system_meta (key, value) VALUES ('schema_version', ?)",
                        (target_version,)
                    )
                    # 3. 提交事务
                    conn.commit()
                    current_version = target_version
                    logger.info(f"[DB] 迁移完成，当前版本: {current_version}")

                except Exception as e:
                    # ── Step 4: 异常处理与回滚 ──
                    # 业务链路：1. 捕获迁移异常 -> 2. 回滚事务（ROLLBACK）-> 
                    # 3. 记录错误日志 -> 4. 抛出异常，阻止系统启动
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
        
        ── 业务链路 ──
        1. 读取 config.json 文件 -> 2. 扫描 SENSITIVE_KEYS 列表中的明文密钥 -> 
        3. 将非空明文密钥加密后写入 secure_keys.json -> 4. 清空 config.json 中的明文密钥 -> 
        5. 后续读取时，ConfigRepo 会自动从 secure_keys.json 解密
        
        幂等性：多次执行不会重复迁移（已加密的密钥会被跳过）
        """
        # ── Step 1: 校验配置文件存在性 ──
        # 业务链路：1. 检查 config.json 是否存在 -> 2. 若不存在则直接返回
        if not os.path.exists(self.config_path):
            return
        
        # ── Step 2: 读取配置文件 ──
        # 业务链路：1. 打开 config.json -> 2. 解析 JSON -> 3. 提取 settings 字段
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        settings = config.get("settings", {})
        crypto = get_crypto_manager()
        
        # ── Step 3: 扫描明文密钥 ──
        # 业务链路：1. 遍历 SENSITIVE_KEYS 列表 -> 2. 检查每个密钥是否在 settings 中存在且非空 -> 
        # 3. 收集需要迁移的明文密钥
        keys_to_migrate = {}
        for key in self.SENSITIVE_KEYS:
            value = settings.get(key, "")
            if value and value.strip():
                keys_to_migrate[key] = value
        
        # ── Step 4: 若无需迁移则直接返回 ──
        if not keys_to_migrate:
            return  # 无需迁移
        
        # ── Step 5: 加载现有的加密存储 ──
        # 业务链路：1. 检查 secure_keys.json 是否存在 -> 2. 若存在则读取现有加密数据 -> 
        # 3. 若不存在则初始化为空字典
        secure_data = {}
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
        
        # ── Step 6: 加密并存储密钥 ──
        # 业务链路：1. 遍历需要迁移的密钥 -> 2. 使用加密管理器加密明文 -> 
        # 3. 存储到 secure_data -> 4. 清空 config.json 中的明文密钥
        for key, value in keys_to_migrate.items():
            # 1. 加密明文密钥
            encrypted = crypto.encrypt_api_key(value)
            # 2. 存储到加密数据字典
            secure_data[key] = encrypted
            # 3. 清空 config.json 中的明文密钥（设为空字符串）
            settings[key] = ""  # 清空明文
        
        # ── Step 7: 原子写入加密文件 ──
        # 业务链路：1. 打开 secure_keys.json 文件 -> 2. 写入加密数据 -> 3. 关闭文件
        with open(self.secure_keys_path, "w", encoding="utf-8") as f:
            json.dump(secure_data, f, indent=4)
        
        # ── Step 8: 原子写入配置文件 ──
        # 业务链路：1. 打开 config.json 文件 -> 2. 写入更新后的配置（明文密钥已清空）-> 3. 关闭文件
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

    def update_task_is_active(self, task_id: int, is_active: int):
        return self._task_repo.update_task_is_active(task_id, is_active)

    def update_any_task_metadata(self, task_id: int, is_archive: bool, imdb_id=None, tmdb_id=None, sub_status=None, title=None, year=None, local_poster_path=None, target_path=None, clean_name=None, season=None, episode=None):
        return self._task_repo.update_any_task_metadata(task_id, is_archive, imdb_id=imdb_id, tmdb_id=tmdb_id, sub_status=sub_status, title=title, year=year, local_poster_path=local_poster_path, target_path=target_path, clean_name=clean_name, season=season, episode=episode)

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
    def get_sibling_poster(self, imdb_id: str, media_type: str, season: int = None, episode: int = None):          return self._stats_repo.get_sibling_poster(imdb_id, media_type, season, episode)
    def check_media_exists(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> bool:   return self._stats_repo.check_media_exists(imdb_id, media_type, season, episode)

    def mark_task_as_ignored_and_inherit(self, task_id: int, imdb_id: str, media_type: str,
                                          season: int = None, episode: int = None,
                                          tmdb_id: int = None):
        """
        🚨 架构级原子操作：专为 PT 做种重复文件设计。[DO NOT SPLIT OR INLINE]

        为什么这个方法不可拆分？
        当文件被 IMDb 重复检测判定为物理副本时，仅将状态改为 ignored 是不够的：
        前端渲染依赖 local_poster_path 字段显示 VHS 破损特效（TAPE ERROR 印章）。
        若该字段为空，前端将出现白板破图，ignored 状态的视觉标识不会触发。

        执行流程：
        1. 跨表检索：从 media_archive（冷表）或 tasks（热表）检索同源海报路径
        -> 2. 状态原子写入：一次性将 ignored 状态、local_poster_path、imdb_id、tmdb_id 写入数据库
        -> 3. 视觉防护：确保前端获得海报路径，正确触发 VHS TAPE ERROR 特效

        任何重构此处代码的开发者，请确保以上三步永远绑定在一起。
        """
        # 1. 跨表查找同源已归档任务的海报路径
        sibling_poster = self.get_sibling_poster(imdb_id, media_type, season, episode)
        if sibling_poster:
            import logging as _log
            _log.getLogger(__name__).info(f"[DB][IGNORE] 已继承同源海报: {sibling_poster}")
        else:
            import logging as _log
            _log.getLogger(__name__).info(f"[DB][IGNORE] 未找到同源海报 (imdb={imdb_id}, type={media_type}, S{season}E{episode})")

        # 2. 原子写入：status=ignored + local_poster_path + imdb_id + tmdb_id
        self._task_repo.update_task_status(
            task_id=task_id,
            status="ignored",
            local_poster_path=sibling_poster,
            tmdb_id=tmdb_id,
            imdb_id=imdb_id if imdb_id else None,
            task_type=media_type,
        )

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
