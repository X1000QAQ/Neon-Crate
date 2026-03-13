"""
base.py - Repository 基类

所有 Repository 继承此基类，通过构造注入共享：
  - _get_conn: DatabaseManager 的线程级连接池方法
  - db_lock:   DatabaseManager 的全局写锁
  - config_path: config.json 文件路径
  - secure_keys_path: secure_keys.json 文件路径

设计原则：
  - 基类本身不包含任何业务逻辑
  - 不自行管理数据库连接，完全依赖注入的 _get_conn
  - 线程安全由注入的 db_lock 保证
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
