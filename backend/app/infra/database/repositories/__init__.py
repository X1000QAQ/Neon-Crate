"""
repositories 包 - DatabaseManager 的 Repository 模式拆分层

架构说明：
- BaseRepository: 所有 Repository 的基类，共享连接池和锁
- 各 Repository 通过构造注入获得 _get_conn 和 db_lock
- DatabaseManager 作为外观类（Facade），内部委托给各 Repository
- 对外接口完全不变，所有调用方无需修改任何 import

拆分阶段：
  Step 1 (当前): 建立目录和 BaseRepository 基类
  Step 2: path_repo.py   — 路径管理仓储
  Step 3: config_repo.py — 配置仓储
  Step 4: stats_repo.py  — 统计仓储
  Step 5: archive_repo.py — 归档仓储
  Step 6: task_repo.py   — 任务仓储
  Step 7: db_manager.py 改造为外观层
  Step 8: npx gitnexus analyze --force 重建索引
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
