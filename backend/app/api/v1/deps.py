"""
FastAPI 依赖注入容器

设计目标：
- 提供统一的 Depends() 可注入依赖
- 替代路由处理函数中的裸调用（如 get_db_manager()）
- 所有依赖函数均幂等：底层仍使用全局单例，不产生额外连接

使用方式：
```python
from app.api.v1.deps import DbDep

async def my_endpoint(db: DbDep):
    db.get_config("tmdb_api_key")
```

优势：
- 类型提示完整：IDE 可自动补全 DatabaseManager 的所有方法
- 测试友好：可通过 app.dependency_overrides 替换为 Mock 对象
- 代码简洁：避免每个路由都重复写 db = get_db_manager()
"""
from typing import Annotated

from fastapi import Depends

from app.infra.database import DatabaseManager, get_db_manager

# ── 数据库依赖 ────────────────────────────────────────────────
# 使用方式：
#   async def my_endpoint(db: DbDep):
#       db.get_config(...)
DbDep = Annotated[DatabaseManager, Depends(get_db_manager)]
