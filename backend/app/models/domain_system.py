"""
系统领域模型 - 配置与系统相关模型
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PathConfig(BaseModel):
    """路径配置模型"""
    id: Optional[int] = None
    type: str = Field(..., description="路径类型: download/library")
    path: str = Field(..., description="物理路径")
    category: str = Field("mixed", description="媒体分类: movie/tv/mixed")
    enabled: bool = Field(True, description="是否启用")


class SystemSettings(BaseModel):
    """系统设置模型"""
    ui_lang: str = "zh"
    min_size_mb: int = Field(50, ge=0, description="最小文件大小(MB)，允许设为0以支持测试")
    filename_clean_regex: str = ""
    cron_enabled: bool = False
    cron_interval_min: int = 60
    auto_process_enabled: bool = False
    auto_scrape: bool = False
    auto_subtitles: bool = False
    
    # API 密钥
    tmdb_api_key: str = ""
    os_api_key: str = ""
    radarr_url: str = ""
    radarr_api_key: str = ""
    sonarr_url: str = ""
    sonarr_api_key: str = ""
    
    # LLM 配置
    llm_provider: str = "cloud"
    llm_cloud_url: str = ""
    llm_cloud_key: str = ""
    llm_cloud_model: str = ""
    llm_local_url: str = ""
    llm_local_key: str = ""
    llm_local_model: str = ""
    
    # AI 人格
    ai_name: str = ""
    ai_persona: str = ""
    expert_archive_rules: str = ""
    master_router_rules: str = ""


class SettingsConfig(BaseModel):
    """完整配置模型"""
    settings: SystemSettings
    paths: List[PathConfig] = []


class AuthStatusResponse(BaseModel):
    """鉴权状态响应"""
    initialized: bool
    message: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    username: str


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class InitRequest(BaseModel):
    """初始化请求"""
    username: str = Field(..., min_length=3, description="用户名（至少3个字符）")
    password: str = Field(..., min_length=6, description="密码（至少6个字符）")


class DeleteBatchRequest(BaseModel):
    """批量删除请求体"""
    ids: List[int]


class PurgeRequest(BaseModel):
    """重置数据库请求体"""
    confirm: str


class ResetSettingsRequest(BaseModel):
    """重置配置请求体"""
    target: str


class ChatRequest(BaseModel):
    """对话请求"""
    message: str


class ChatResponse(BaseModel):
    """对话响应"""
    response: str
    action: Optional[str] = None
