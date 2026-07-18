"""
媒体领域模型 - 媒体任务、扫描响应与仪表盘统计契约

职责：
- 定义媒体任务相关的 Pydantic 请求 / 响应模型。
- 为 FastAPI 自动生成 OpenAPI Schema，并在路由层执行序列化与类型校验。
- 屏蔽数据库字段差异，例如数据库使用 `type`，对外 API 使用 `media_type`。

模型边界：
- 本文件只描述 API 数据契约，不访问数据库，也不执行刮削、扫描或字幕逻辑。
- 字段名、默认值和可空性直接影响前端渲染与接口兼容性，修改前必须评估调用方。
- `clean_name`、`year`、`season`、`episode` 等字段承载上游 AI / 刮削结果，不在模型层重新推断。

核心模型：
- `StatsResponse`：控制台大屏统计数据。
- `ScanResponse`：扫描、刮削、字幕等后台任务触发后的通用响应。
- `Task`：媒体任务完整响应模型，统一表达热表与冷表任务。
"""
from typing import Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class StatsResponse(BaseModel):
    """
    控制台大屏统计数据响应模型。

    数据来源：
    - `movies` / `tv_shows`：媒体任务和归档记录聚合后的分类数量。
    - `pending`：等待处理的扫描任务数量。
    - `completed`：已经完成归档或可视为完成的媒体数量。

    注意：
    - 这是展示层聚合结果，不是数据库表结构的一一映射。
    - 字段保持非空整数，避免前端大屏组件处理 `null`。
    """
    movies: int = 0
    tv_shows: int = 0
    pending: int = 0
    completed: int = 0


class ScanResponse(BaseModel):
    """
    后台任务触发后的通用响应模型。

    使用场景：
    - 物理扫描：接收用户或定时巡逻触发，后台发现新文件。
    - 全量刮削：对待处理任务执行元数据识别。
    - 字幕补完：对已归档媒体执行字幕搜索。

    字段契约：
    - `message` 面向前端 Toast 或状态提示。
    - `task_id` 预留给异步任务追踪；当前没有任务 ID 时可以为空。
    """
    message: str
    task_id: Optional[str] = None


class Task(BaseModel):
    """
    媒体任务完整响应模型。

    字段命名：
    - 对外使用 `media_type`，避免把数据库保留字段风格的 `type` 直接暴露给前端。
    - `populate_by_name=True` 允许路由层按字段名构造模型，减少别名迁移成本。

    冷热表语义：
    - `is_archive=False` 表示记录来自热表 `tasks`。
    - `is_archive=True` 表示记录来自冷表 `media_archive`，更新时通常要使用 `original_task_id` 寻址。

    状态流转：
    - `pending` → `scraped` → `archived`：正常扫描、刮削、归档流程。
    - `pending` → `failed`：刮削、下载或搬运失败。
    - 任意状态 → `ignored`：重复文件或用户主动忽略。

    注意：
    - `year` 兼容字符串和整数，是为了接住 SQLite TEXT 字段与外部 API 的混合输入。
    - 模型层不重新解析文件名，也不承担物理正则清洗职责。
    """
    model_config = ConfigDict(populate_by_name=True)

    id: int
    file_path: str
    file_name: Optional[str] = None
    clean_name: Optional[str] = None
    media_type: str = Field(..., description="媒体类型: movie | tv")
    status: str = Field(default="pending", description="任务状态: pending | archived | failed | ignored | scraped")
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: Optional[str] = None
    # DB 层 year 可能以 TEXT 形式返回；为保持前后端契约一致，这里允许 int/str 双形态
    year: Optional[Union[int, str]] = None
    poster_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    target_path: Optional[str] = None
    sub_status: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    created_at: str = Field(default="", description="创建时间（ISO格式），空串为兜底")
    is_archive: bool = Field(default=False, description="冷热表寻址标志：True 为冷表(media_archive)，False 为热表(tasks)")
