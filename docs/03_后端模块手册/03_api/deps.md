# deps — 依赖注入容器

**文件路径**: `backend/app/api/v1/deps.py`

---

## 职责

提供统一的 `Depends()` 可注入依赖，替代路由处理函数中的裸 `get_db_manager()` 调用。

---

## 定义

```python
from typing import Annotated
from fastapi import Depends
from app.infra.database import DatabaseManager, get_db_manager

# 类型别名：在路由函数参数中直接使用
DbDep = Annotated[DatabaseManager, Depends(get_db_manager)]
```

---

## 使用方式

```python
from app.api.v1.deps import DbDep

@router.get("/settings")
async def get_settings(db: DbDep):
    config = db.get_all_config()
    return config

@router.post("/settings")
async def update_settings(config: SettingsConfig, db: DbDep):
    db.save_all_config(config.model_dump())
```

---

## 当前使用情况

| 文件 | 注入方式 |
|------|----------|
| `03_api/tasks/settings_router.py` | `db: DbDep` ✅ |
| `03_api/tasks/media_router.py` | `db: DbDep = None` ✅ |
| `03_api/system.py` | `db: DbDep` ✅ |
| `03_api/agent.py` | 不需要（Agent 通过构造函数注入）|
| 后台任务函数 | `get_db_manager()` 直调（FastAPI 规范，非缺陷）|

---

## 说明

`Depends(get_db_manager)` 底层仍返回全局单例，不产生额外连接。  
其价值在于：路由函数签名中明确声明数据库依赖，便于测试时 Mock 替换。
