"""



核心配置模块 - 环境变量、数据路径与运行参数







职责：



- 使用 `pydantic-settings` 从环境变量和 `.env` 文件加载运行配置。



- 为服务监听、CORS、Docker 存储挂载、数据库路径、JWT 等提供统一默认值。



- 通过 `lru_cache` 暴露全局单例，避免多处重复解析环境变量。







配置优先级：



1. 环境变量，例如 `PORT=9000 python -m app.main`。



2. 项目根目录 `.env` 文件。



3. `Settings` 类中定义的默认值。







路径约定：



- `DOCKER_STORAGE_PATH` 指向容器内媒体挂载点，默认 `/storage`。



- `DB_PATH`、`CONFIG_PATH` 默认落在 `data/`，由数据库和配置仓储模块使用。



- 本模块只提供路径字符串，不负责创建数据库、配置文件或目录。



"""



import os



from typing import Optional



from pydantic_settings import BaseSettings



from functools import lru_cache











class Settings(BaseSettings):



    """

    应用运行配置。



    字段可通过环境变量或 `.env` 覆盖，默认值适配单容器 AIO 部署。

    本类只描述配置，不执行目录创建、数据库初始化或网络检查。

    """



    



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



    """
    获取应用配置单例。

    `lru_cache` 保证环境变量只解析一次，避免路由、生命周期和静态资源装配阶段重复实例化。
    """



    return Settings()











# 导出配置实例



settings = get_settings()



