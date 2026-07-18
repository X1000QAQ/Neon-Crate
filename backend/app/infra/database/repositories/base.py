"""
base.py - Repository 基类与共享依赖容器

职责：
- 为所有仓储类保存 `DatabaseManager` 注入的连接获取函数、全局锁和配置文件路径。
- 提供 `_like()` 工具方法，对 SQL LIKE 搜索词进行通配符转义。
- 保持仓储层的依赖形态一致，避免每个 Repository 重复声明连接和锁字段。

设计边界：
- 基类不包含业务 SQL，不直接创建 SQLite 连接。
- 线程安全由注入的 `db_lock` 和 `DatabaseManager._get_conn()` 共同保证。
- 子类负责具体表、配置文件或业务查询逻辑。
"""
import sqlite3
import threading
from typing import Callable


class BaseRepository:
    """
    Repository 基类：共享 DatabaseManager 的连接池和锁。

    Args:
        get_conn_fn: DatabaseManager._get_conn 的引用，返回当前线程的 SQLite 连接
        db_lock:     DatabaseManager.db_lock 的引用，threading.Lock 实例
        config_path: config.json 的文件路径
        secure_keys_path: secure_keys.json 的文件路径
    """

    def __init__(
        self,
        get_conn_fn: Callable[[], sqlite3.Connection],
        db_lock: threading.Lock,
        config_path: str = "data/config.json",
        secure_keys_path: str = "data/secure_keys.json",
    ):
        self._get_conn = get_conn_fn
        self.db_lock = db_lock
        self.config_path = config_path
        self.secure_keys_path = secure_keys_path

    @staticmethod
    def _like(keyword: str) -> str:
        """将搜索词转义为安全的 LIKE 模式，防止 % 和 _ 被解释为通配符。"""
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"
