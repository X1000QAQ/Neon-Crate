# main.py — 应用入口

**文件路径**: `backend/app/main.py`  
**代码行数**: 12 行（极简入口）

---

## 职责

`main.py` 是 uvicorn 的挂载点，**不承担任何业务逻辑**。  
全部配置委托给 `app_factory.py` 和 `lifespan.py`。

---

## 源码

```python
from app.core.app_factory import create_app
from app.core.lifespan import lifespan
from app.infra.config import settings

app = create_app(lifespan=lifespan)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        workers=1,
    )
```

---

## 启动方式

```bash
# 生产启动（通过 uvicorn 直接挂载）
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 开发调试
python -m app.main

# Docker 内启动（Dockerfile CMD）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

---

## 依赖关系

```
main.py
  ├── app.core.app_factory  → create_app()  （应用工厂）
  ├── app.core.lifespan     → lifespan()    （生命周期管理器）
  └── app.infra.config      → settings      （HOST / PORT 配置）
```

→ 详见 [app_factory.md](01_core/app_factory.md) 和 [lifespan.md](01_core/lifespan.md)
