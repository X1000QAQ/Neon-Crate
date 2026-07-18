"""
数据库基础设施包入口。

导出：
- `DatabaseManager`：SQLite 初始化、迁移和仓储外观。
- `get_db_manager`：全局数据库门面单例。

说明：导入本包不会立即初始化数据库，只有调用 `get_db_manager()` 时才创建实例。
"""
from .db_manager import DatabaseManager, get_db_manager

__all__ = ["DatabaseManager", "get_db_manager"]
