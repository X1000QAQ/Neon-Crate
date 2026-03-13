# config — 环境变量配置模块

**文件路径**: `backend/app/infra/config/__init__.py`  
**核心类**: `Settings(BaseSettings)`  
**单例访问**: `from app.infra.config import settings`

---

## 职责

通过 `pydantic-settings` 管理所有环境变量和应用静态配置，支持 `.env` 文件覆盖。

---

## 配置项一览

### 应用基础

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `APP_NAME` | `"Neon Crate"` | 应用名称 |
| `APP_VERSION` | `"1.0.0"` | 版本号 |
| `HOST` | `"0.0.0.0"` | 监听地址 |
| `PORT` | `8000` | 监听端口 |
| `DEBUG` | `False` | 调试模式 |

### CORS

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `CORS_ORIGINS` | `["http://localhost:3000", ...]` | 允许的前端源 |

### 存储路径

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `DOCKER_STORAGE_PATH` | `"/storage"` | Docker 影音挂载点 |
| `DB_PATH` | `"data/media_database.db"` | SQLite 数据库路径 |
| `CONFIG_PATH` | `"data/config.json"` | 运行时配置文件路径 |

### 日志

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `LOG_LEVEL` | `"INFO"` | 日志级别 |

### API

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `API_V1_PREFIX` | `"/api/v1"` | API 路由前缀 |

### JWT

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `JWT_SECRET_KEY` | `"your-secret-key-..."` | ⚠️ 生产必须通过 `.env` 覆盖 |
| `JWT_ALGORITHM` | `"HS256"` | 签名算法 |
| `JWT_EXPIRE_DAYS` | `7` | Token 有效期（天）|

---

## 使用方式

```python
from app.infra.config import settings

print(settings.HOST)       # "0.0.0.0"
print(settings.PORT)       # 8000
print(settings.API_V1_PREFIX)  # "/api/v1"
```

`get_settings()` 使用 `@lru_cache()` 装饰，全局单例，无额外开销。

---

## .env 文件示例

```env
HOST=0.0.0.0
PORT=8000
DEBUG=false
JWT_SECRET_KEY=your-production-secret-key-here
LOG_LEVEL=INFO
DOCKER_STORAGE_PATH=/mnt/media
```

`.env.example` 已提交至仓库，`.env` 已加入 `.gitignore`。
