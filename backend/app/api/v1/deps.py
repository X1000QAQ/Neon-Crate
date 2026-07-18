"""
FastAPI 依赖注入容器。

职责：
- 提供可复用的 `Depends()` 类型别名，减少路由函数中的重复样板代码。
- 将数据库管理器作为显式依赖注入到路由层，便于测试替换和类型补全。
- 保持底层仍使用全局单例，不为每次请求重复创建数据库管理器。

当前依赖：
- `DbDep`：注入 `DatabaseManager`，供配置、任务、统计和归档接口调用。

维护提示：
- 本文件只定义依赖类型，不应放入具体业务逻辑。
- 后续新增依赖时应保持幂等，避免在依赖解析阶段产生昂贵副作用。
"""
from typing import Annotated

from fastapi import Depends

from app.infra.database import DatabaseManager, get_db_manager

# ── 数据库依赖 ────────────────────────────────────────────────
# 使用方式：
#   async def my_endpoint(db: DbDep):
#       db.get_config(...)
DbDep = Annotated[DatabaseManager, Depends(get_db_manager)]
