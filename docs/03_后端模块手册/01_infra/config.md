# 配置模块手册 - `app/infra/config/`

> 路径：`backend/app/infra/config/__init__.py`

---

## 一、模块概述

基于 **pydantic-settings** 的环境变量配置管理模块。提供全局单例 `settings` 对象，支持 `.env` 文件读取和环境变量覆盖，带 `lru_cache` 缓存避免重复解析。

---

## 二、核心类

### `Settings(BaseSettings)`

| 字段 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `APP_NAME` | str | `"Neon Crate"` | 应用名称 |
| `APP_VERSION` | str | `"1.0.0"` | 应用版本 |
| `HOST` | str | `"0.0.0.0"` | 监听地址 |
| `PORT` | int | `8000` | 监听端口 |
| `DEBUG` | bool | `False` | 调试模式 |
| `CORS_ORIGINS` | list | `["http://localhost:3000"]` | CORS 白名单 |
| `DOCKER_STORAGE_PATH` | str | `"/storage"` | Docker 媒体挂载点 |
| `DB_PATH` | str | `"data/media_database.db"` | SQLite 数据库路径 |
| `CONFIG_PATH` | str | `"data/config.json"` | 应用配置文件路径 |
| `LOG_LEVEL` | str | `"INFO"` | 日志级别 |
| `API_V1_PREFIX` | str | `"/api/v1"` | API 路由前缀 |
| `JWT_SECRET_KEY` | str | `"your-secret-key..."` | JWT 签名密钥（生产必须替换）|
| `JWT_ALGORITHM` | str | `"HS256"` | JWT 算法 |
| `JWT_EXPIRE_DAYS` | int | `7` | Token 过期天数 |

---

## 三、核心函数

### `get_settings() -> Settings`

```python
@lru_cache()
def get_settings() -> Settings:
    return Settings()
```

- 带 `lru_cache` 缓存，进程生命周期内只实例化一次
- 导出的 `settings` 是全局单例，直接 import 使用

---

## 四、使用方式

```python
from app.infra.config import settings

print(settings.APP_NAME)   # "Neon Crate"
print(settings.PORT)       # 8000
```

---

## 五、环境变量覆盖

支持通过 `.env` 文件或系统环境变量覆盖任意字段：

```env
PORT=9000
DEBUG=true
JWT_SECRET_KEY=my-production-secret
DOCKER_STORAGE_PATH=/mnt/media
```

---

## 六、注意事项

- `JWT_SECRET_KEY` 默认值仅用于开发，**生产环境必须通过 `.env` 替换**
- `DOCKER_STORAGE_PATH` 默认为 `/storage`，本地开发时会回退到 `data/posters/`（在 `main.py` 中处理）
- `lru_cache` 意味着修改 `.env` 后需重启服务才能生效

---

*最后更新：2026-03-11*
