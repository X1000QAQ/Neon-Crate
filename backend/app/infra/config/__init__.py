"""
核心配置模块 - 环境变量与系统配置管理

设计模式：
- 使用 pydantic-settings BaseSettings，支持环境变量覆盖
- lru_cache 单例：全局只实例化一次，避免重复读取 .env
- 所有配置均有默认值，可直接开箱即用

配置层级（优先级从高到低）：
1. 环境变量（如 PORT=9000 python -m app.main）
2. .env 文件（项目根目录）
3. 代码中的默认值

主要配置项：
- HOST/PORT：服务监听地址（默认 0.0.0.0:8000）
- CORS_ORIGINS：允许的前端域名
- DOCKER_STORAGE_PATH：Docker 影音挂载点（默认 /storage）
- DB_PATH：SQLite 数据库路径（默认 data/media_database.db）
- API_V1_PREFIX：API 路由前缀（默认 /api/v1）
- JWT_EXPIRE_DAYS：JWT 有效期（默认 7 天）
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """应用配置类 - 支持环境变量覆盖"""
    
    # 应用基础信息
    APP_NAME: str = "Neon Crate"
    APP_VERSION: str = "1.0.0"
    APP_DESCRIPTION: str = "Digital Container Engine for structured data orchestration"
    
    # 服务器配置
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # CORS 配置
    # AIO 单容器部署：前后端同域，CORS 实际不触发；但局域网直接访问 /api/v1/* 时
    # 若浏览器发送 Origin 头，仍需放行。生产环境使用通配符以兼容任意局域网 IP。
    # 如需收紧，可通过环境变量 CORS_ORIGINS 覆盖为具体地址列表。
    CORS_ORIGINS: list = ["*"]
    
    # Docker 环境统一挂载点
    DOCKER_STORAGE_PATH: str = "/storage"
    
    # 数据库配置
    DB_PATH: str = "data/media_database.db"
    CONFIG_PATH: str = "data/config.json"
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # API 配置
    API_V1_PREFIX: str = "/api/v1"
    
    # JWT 配置
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_DAYS: int = 7

    # 运行环境: development / production
    APP_ENV: str = "production"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例 (带缓存)"""
    return Settings()


# 导出配置实例
settings = get_settings()
