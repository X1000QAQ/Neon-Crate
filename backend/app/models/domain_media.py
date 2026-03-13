"""
媒体领域模型 - Pydantic 数据模型定义

设计说明：
- 所有模型均继承 Pydantic BaseModel，自动验证数据类型
- 用于 FastAPI 请求/响应的序列化与反序列化
- 统一字段命名规范，避免前后端字段名不一致

核心模型：
- StatsResponse：控制台大屏统计数据
- ScanResponse：扫描/任务触发的通用响应
- Task：媒体任务完整模型（统一使用 media_type，而非数据库的 type 字段）
"""
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class StatsResponse(BaseModel):
    """
    控制台大屏统计数据响应模型

    字段说明：
    - movies：媒体库中的电影数量（来自缓存，由刮削任务更新）
    - tv_shows：媒体库中的剧集集数（来自缓存，由刮削任务更新）
    - pending：待处理任务数量（实时统计）
    - completed：已完成任务数量（实时统计）
    """
    movies: int = 0
    tv_shows: int = 0
    pending: int = 0
    completed: int = 0


class ScanResponse(BaseModel):
    """
    扫描/任务触发的通用响应模型

    使用场景：
    - POST /scan：触发物理扫描
    - POST /scrape_all：触发全量刮削
    - POST /find_subtitles：触发字幕补完
    """
    message: str
    task_id: Optional[str] = None


class Task(BaseModel):
    """
    媒体任务完整模型

    字段命名说明：
    - 使用 media_type（而非数据库的 type 字段），与前端契约对齐
    - populate_by_name=True：允许通过字段名或别名赋值

    状态流转：
    pending → scraped → archived（正常归档流程）
    pending → failed（刮削/搬运失败）
    any → ignored（手动跳过或重复文件）
    """
    model_config = ConfigDict(populate_by_name=True)

    id: int
    file_path: str
    file_name: Optional[str] = None
    media_type: str = Field(..., description="媒体类型: movie | tv")
    status: str = Field(default="pending", description="任务状态: pending | scraped | failed | archived")
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    title: Optional[str] = None
    year: Optional[int] = None
    poster_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    target_path: Optional[str] = None
    sub_status: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    created_at: Optional[str] = None
