"""
数据库仓储包入口。

Repository 拆分：
- `BaseRepository`：共享连接获取函数、数据库锁和配置路径。
- `PathRepo`：管理下载目录和媒体库路径配置。
- `ConfigRepo`：管理普通配置、敏感密钥和提示词文件化。
- `StatsRepo`：提供仪表盘、媒体墙和重复检测只读查询。
- `ArchiveRepo`：管理冷表和冷热表归档流转。
- `TaskRepo`：管理热表任务生命周期。

架构边界：
- `DatabaseManager` 是外观层，负责对旧调用方保持兼容。
- 各 Repository 不自行创建 SQLite 连接，只使用注入的线程级连接和锁。
"""

from .base import BaseRepository
from .path_repo import PathRepo
from .config_repo import ConfigRepo
from .stats_repo import StatsRepo
from .archive_repo import ArchiveRepo
from .task_repo import TaskRepo

__all__ = [
    "BaseRepository",
    "PathRepo",
    "ConfigRepo",
    "StatsRepo",
    "ArchiveRepo",
    "TaskRepo",
]
