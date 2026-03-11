"""
媒体领域模型 - Pydantic 数据模型定义
"""
from typing import Optional
from pydantic import BaseModel


class StatsResponse(BaseModel):
    """统计数据响应"""
    movies: int = 0
    tv_shows: int = 0
    pending: int = 0
    completed: int = 0


class ScanResponse(BaseModel):
    """扫描响应"""
    message: str
    task_id: Optional[str] = None
