"""
核心配置模块 - 环境变量与系统配置管理
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
    CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
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
    
    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例 (带缓存)"""
    return Settings()


# 导出配置实例
settings = get_settings()
