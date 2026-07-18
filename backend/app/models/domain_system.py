"""
系统领域模型 - 配置、鉴权、操作请求与 AI 对话契约

职责：
- 定义系统设置、路径配置、认证请求、批量操作和 AI 对话相关 Pydantic 模型。
- 作为 FastAPI 路由的请求体 / 响应体契约，驱动运行时校验和 OpenAPI 文档生成。
- 将配置仓储中的 `settings` 与 `paths` 结构转化为稳定的前后端 API 形态。

重要边界：
- 本文件只定义数据形状，不读取 `config.json`，不解密 API Key，也不触发业务动作。
- 字段默认值是前端表单、初始化流程和配置保存链路的兼容基础，不能随意删除。
- 系统已废弃用户自定义“物理正则清洗”配置，因此 `SystemSettings` 不包含 `filename_clean_regex`。

模型分类：
- 配置模型：`PathConfig`、`SystemSettings`、`SettingsConfig`。
- 认证模型：`AuthStatusResponse`、`TokenResponse`、`LoginRequest`、`InitRequest`。
- 操作模型：`DeleteBatchRequest`、`PurgeRequest`、`ResetSettingsRequest`。
- AI 对话模型：`ChatRequest`、`PendingActionPayload`、`CandidateItem`、`ChatResponse`。
"""
from typing import Optional, List
from pydantic import BaseModel, Field


class PathConfig(BaseModel):
    """
    路径配置模型。

    路径类型：
    - `download`：下载目录，通常对应 PT 客户端或下载器的完成目录。
    - `library` / `media` / `storage`：媒体库目录，归档阶段会把硬链接或整理后的文件放入这里。

    媒体分类：
    - `movie`：电影库。
    - `tv`：剧集库。
    - `mixed`：混合目录，主要用于兼容旧配置或临时目录。

    注意：
    - `path` 是用户配置的物理路径字符串，模型层不检查目录是否存在。
    - 目录可用性、权限和“1 个电影库 + 1 个剧集库”约束由服务层和仓储层处理。
    """
    id: Optional[int] = None
    type: str = Field(..., description="路径类型: download/library")
    path: str = Field(..., description="物理路径")
    category: str = Field("mixed", description="媒体分类: movie/tv/mixed")
    enabled: bool = Field(True, description="是否启用")


class SystemSettings(BaseModel):
    """
    系统设置完整模型。

    配置分类：
    - 基础设置：界面语言、最小文件大小、自动处理开关。
    - 定时巡逻：巡逻间隔、自动刮削、自动字幕补完。
    - 外部服务：TMDB、OpenSubtitles、Radarr、Sonarr 的连接信息。
    - LLM 双引擎：云端兼容接口与本地 Ollama 接口。
    - AI 人格：助手名称、系统人格、归档专家提示词、总控路由提示词。
    - 多语言偏好：字幕、海报和重命名语言。
    - 文件格式过滤：扫描和字幕识别使用的扩展名字符串。

    安全边界：
    - API Key 字段在 API 契约中仍是字符串，便于设置页编辑。
    - 真正的加密存储由 `ConfigRepo` 和 `CryptoManager` 完成，模型层不处理密文。

    废弃字段说明：
    - 不包含 `filename_clean_regex`。
    - 当前系统不再提供用户自定义文件名物理正则清洗能力。
    - 文件名语义识别由 AI Agent、提示词和刮削链路承担。
    """
    ui_lang: str = "zh"
    min_size_mb: int = Field(50, ge=0, description="最小文件大小(MB)，允许设为0以支持测试")
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

    # 文件格式过滤
    supported_video_exts: str = ""
    supported_subtitle_exts: str = ""


class SettingsConfig(BaseModel):
    """
    完整配置顶层容器模型。

    API 契约：
    - `settings` 对应系统配置表单。
    - `paths` 对应下载目录和媒体库目录列表。

    使用场景：
    - `GET /settings`：后端读取配置仓储后返回该结构。
    - `POST /settings`：前端提交完整配置时使用同一结构。
    """
    settings: SystemSettings
    paths: List[PathConfig] = []


class AuthStatusResponse(BaseModel):
    """
    鉴权初始化状态响应模型。

    使用场景：
    - 前端启动时检查系统是否已经完成管理员初始化。
    - 未初始化时引导进入首次设置流程。

    字段说明：
    - `initialized`：是否已经存在可登录管理员。
    - `message`：给前端展示的状态说明。
    """
    initialized: bool
    message: str


class TokenResponse(BaseModel):
    """
    登录成功后的 Token 响应模型。

    字段说明：
    - `access_token`：后端签发的 JWT。
    - `token_type`：固定为 `bearer`，供前端拼接 Authorization 头。
    - `username`：当前登录用户名称，用于界面展示。
    """
    access_token: str
    token_type: str = "bearer"
    username: str


class LoginRequest(BaseModel):
    """
    登录请求模型。

    说明：
    - `username` 和 `password` 是用户输入的明文凭据。
    - 密码校验、哈希比对和失败处理在鉴权服务中完成，模型层只负责字段存在性。
    """
    username: str
    password: str


class InitRequest(BaseModel):
    """
    首次初始化管理员请求模型。

    校验规则：
    - `username` 至少 3 个字符。
    - `password` 至少 6 个字符。

    说明：
    - 只用于系统尚未初始化时创建首个管理员。
    - 密码持久化前的哈希处理由鉴权逻辑完成。
    """
    username: str = Field(..., min_length=3, description="用户名（至少3个字符）")
    password: str = Field(..., min_length=6, description="密码（至少6个字符）")


class DeleteBatchRequest(BaseModel):
    """
    批量删除任务请求模型。

    字段说明：
    - `ids` 是前端选中的任务 ID 列表。
    - 后端会同时尝试清理热表 `tasks` 和冷表 `media_archive` 中的对应记录。

    注意：
    - 模型层不校验 ID 是否存在。
    - 空列表、权限和事务一致性由路由或仓储层处理。
    """
    ids: List[int]


class PurgeRequest(BaseModel):
    """
    全量清空任务请求模型。

    字段说明：
    - `confirm` 必须由路由层校验为约定确认词，防止误触发高危操作。

    风险说明：
    - 该请求对应清空任务表和归档表的“核弹按钮”。
    - 模型层只承载用户输入，不执行删除动作。
    """
    confirm: str


class ResetSettingsRequest(BaseModel):
    """
    配置重置请求模型。

    字段说明：
    - `target` 表示重置目标分类，例如 `ai` 或 `formats`。

    注意：
    - 有效枚举由 `ConfigRepo.RESET_TARGETS_MAP` 决定。
    - 模型层不内置枚举，是为了保持与仓储层的数据驱动映射兼容。
    """
    target: str


class ChatRequest(BaseModel):
    """
    AI 对话请求模型。

    字段说明：
    - `message` 是用户输入的自然语言指令或闲聊内容。
    - 长度限制用于保护 LLM 调用和后端日志，避免异常超长输入进入 Agent 链路。

    后续链路：
    - AI Agent 会识别扫描、刮削、字幕、下载、本地搜索和普通聊天等意图。
    - 模型层不解析意图，只保证请求形状合法。
    """
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="用户消息（长度限制：防止超长输入）"
    )


class PendingActionPayload(BaseModel):
    """
    待用户确认的操作载荷模型。

    使用场景：
    - AI 识别到下载等高风险意图后，后端不会立刻执行动作。
    - 路由层会先构造该载荷，前端据此渲染全屏确认界面或确认卡片。
    - 用户授权后，后端再根据 `action` 和元数据执行后续流程。

    字段分组：
    - 基础字段：`action`、`label`、`description`，用于描述待执行动作。
    - 下载元数据：`title`、`year`、`poster_url`、`overview`、`media_type`、`tmdb_id`。
    - 名称兜底：`clean_name`、`en_name`，用于 TMDB 信息不足或候选回填。
    - 查重审计：`is_duplicate`、`existing_status`，用于提示用户库内已有或监控状态。

    注意：
    - 该模型只是授权决策层的数据包，不代表任务已经执行。
    - 前端文案应体现“等待确认”，避免让用户误以为已经开始下载。
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
    候选影视条目模型。

    使用场景：
    - 用户输入模糊片名或系列名时，后端返回多个候选项。
    - 前端渲染为按钮组或列表，让用户明确选择目标条目。

    字段说明：
    - `title`：候选展示名。
    - `year`：候选年份，未知时为空字符串。
    - `media_type`：候选类型，默认按电影处理。
    - `tmdb_id`：可选的 TMDB 精确标识。
    """
    title: str
    year: str = ""
    media_type: str = "movie"
    tmdb_id: Optional[int] = None


class ChatResponse(BaseModel):
    """
    AI 对话响应模型。

    字段说明：
    - `response`：展示给用户的自然语言回复。
    - `action`：意图代码，例如扫描、刮削、字幕、下载或本地搜索；为空表示普通聊天。
    - `pending_action`：需要用户确认的高风险操作载荷。
    - `candidates`：模糊搜索或系列名解析得到的候选项列表。
    - `engine_tag`：LLM 引擎血缘标记，用于诊断云端、本地或降级链路。

    前端契约：
    - `pending_action` 非空时，前端应进入确认 UI，而不是直接视为执行完成。
    - `candidates` 非空时，前端应渲染可选择候选，不应让 AI 擅自挑选系列中的某一部。
    """
    response: str
    action: Optional[str] = None
    pending_action: Optional[PendingActionPayload] = None
    candidates: List[CandidateItem] = []
    engine_tag: Optional[str] = None  # v1.0.0 血缘溯源："cloud" | "local" | "local->cloud"
