"""
系统领域模型 - 配置与系统相关 Pydantic 模型

设计说明：
- 所有模型均继承 Pydantic BaseModel，自动验证数据类型
- 用于 FastAPI 请求/响应的序列化与反序列化

核心模型分类：

配置模型：
- PathConfig：路径配置（下载目录、媒体库目录）
- SystemSettings：完整系统设置（API 密钥、LLM 配置、AI 人格等）
- SettingsConfig：顶层配置容器（settings + paths）

认证模型：
- AuthStatusResponse：系统初始化状态
- TokenResponse：JWT Token 响应
- LoginRequest：登录请求
- InitRequest：首次初始化请求（用户名≥3字符，密码≥6字符）

操作模型：
- DeleteBatchRequest：批量删除任务请求
- PurgeRequest：全量清空（核弹按钮，需输入 CONFIRM）
- ResetSettingsRequest：重置配置请求（target: ai|regex）

AI 对话模型：
- ChatRequest：用户消息
- ChatResponse：AI 回复 + 意图代码
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PathConfig(BaseModel):
    """
    路径配置模型

    路径类型（type）：
    - download：下载目录（PT 客户端的下载目标目录）
    - library：媒体库目录（Plex/Jellyfin 的媒体库目录）

    媒体分类（category）：
    - movie：电影库
    - tv：剧集库
    - mixed：混合（不区分类型）
    """
    id: Optional[int] = None
    type: str = Field(..., description="路径类型: download/library")
    path: str = Field(..., description="物理路径")
    category: str = Field("mixed", description="媒体分类: movie/tv/mixed")
    enabled: bool = Field(True, description="是否启用")


class SystemSettings(BaseModel):
    """
    系统设置完整模型
    
    配置分类：
    
    基础设置：
    - ui_lang：界面语言（zh/en）
    - min_size_mb：最小文件大小过滤（0 表示不过滤，用于测试）
    - filename_clean_regex：文件名清洗正则表达式
    
    定时巡逻：
    - cron_enabled：是否开启定时巡逻
    - cron_interval_min：巡逻间隔（分钟）
    - auto_scrape：是否自动刮削
    - auto_subtitles：是否自动搜索字幕
    
    外部服务 API：
    - tmdb_api_key：TMDB 元数据 API 密钥
    - os_api_key：OpenSubtitles 字幕 API 密钥
    - radarr_url/api_key：Radarr 电影下载管理
    - sonarr_url/api_key：Sonarr 剧集下载管理
    
    LLM 配置（双引擎）：
    - llm_provider：cloud（云端）或 local（本地 Ollama）
    - llm_cloud_*：云端 API（OpenAI/DeepSeek 兼容接口）
    - llm_local_*：本地 Ollama 接口
    
    AI 人格：
    - ai_name：AI 助手名称
    - ai_persona：AI 人格设定（System Prompt）
    - expert_archive_rules：AI 归档专家规则（识别影视文件）
    - master_router_rules：总控路由规则（意图识别）
    
    多语言偏好：
    - subtitle_lang：字幕语言（zh/en）
    - poster_lang：海报语言（zh/en）
    - rename_lang：重命名语言（zh/en）
    """
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
    llm_cloud_enabled: bool = True   # 云端引擎物理开关
    llm_local_enabled: bool = False  # 本地引擎物理开关
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

    # 多语言偏好
    subtitle_lang: str = "zh"
    poster_lang: str = "zh"
    rename_lang: str = "zh"


class SettingsConfig(BaseModel):
    """
    完整配置顶层容器模型

    作为 GET/POST /settings 的请求和响应体，
    包含系统设置和路径配置两个部分。
    """
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
    """
    AI 对话请求模型

    message：用户输入的消息（自然语言）
    AI Agent 会根据内容识别意图并路由到对应处理逻辑
    """
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="用户消息（长度限制：防止超长输入）"
    )


class PendingActionPayload(BaseModel):
    """
    授权决策层载荷：封装需要用户视觉确认的指令及其关联元数据

    下载意图携带 TMDB 元数据，供前端渲染全屏确认界面；
    其他意图仅携带基础字段。

    action:      意图代码（来自 AIActionEnum 白名单）
    label:       操作名称
    description: 操作摘要
    title:       TMDB 确认片名
    year:        上映年份
    poster_url:  TMDB 海报完整 URL
    overview:    剧情简介
    media_type:  movie | tv
    tmdb_id:     TMDB ID（用于精确下载）
    clean_name:  原始中文片名（fallback 用）
    en_name:     英文片名
    """
    action: str
    label: str
    description: str = ""
    # 下载意图专属元数据
    title: Optional[str] = None
    year: Optional[str] = None
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    media_type: Optional[str] = None
    tmdb_id: Optional[int] = None
    clean_name: Optional[str] = None
    en_name: Optional[str] = None
    # 查重审计结果
    is_duplicate: bool = False
    existing_status: Optional[str] = None  # 如「已在库中」「正在监控」「文件缺失」


class CandidateItem(BaseModel):
    """
    候选影视条目（结构化候选列表单项）
    """
    title: str
    year: str = ""
    media_type: str = "movie"
    tmdb_id: Optional[int] = None


class ChatResponse(BaseModel):
    """
    AI 对话响应模型

    response：       AI 回复的文本内容
    action：         意图代码（如 ACTION_SCAN / DOWNLOAD 等），
                    前端根据此字段触发对应的 UI 操作；None 表示纯聊天
    pending_action： 待确认指令载荷，非 None 时前端渲染「指令确认卡片」，等待用户授权
    candidates：     结构化候选列表，非空时前端渲染交互式选项按钮组
    """
    response: str
    action: Optional[str] = None
    pending_action: Optional[PendingActionPayload] = None
    candidates: List[CandidateItem] = []
    engine_tag: Optional[str] = None  # V2.0 血缘溯源："cloud" | "local" | "local->cloud"
