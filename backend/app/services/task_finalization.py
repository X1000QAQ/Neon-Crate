"""
任务终态更新统一封装模块

职责：
- 提供 TaskFinalizationMetadata 数据类封装任务完成时的元数据
- 提供 finalize_task() 统一接口封装 update_task_title_year + update_task_status
- 明确业务契约：只用于终态状态（archived / scraped / failed）

设计模式：
- 数据传输对象（DTO）：TaskFinalizationMetadata
- 门面模式（Facade）：finalize_task() 简化复杂的状态更新流程
- 单一职责原则（SRP）：专注任务终态更新逻辑

使用场景：
- 正常刮削完成（status="archived"）
- Nuclear 重构完成（status="archived"）
- 刮削失败（status="failed"）
"""
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class TaskFinalizationMetadata:
    """
    任务终态更新元数据封装
    
    职责：
    - 封装任务完成时需要更新的所有元数据字段
    - 提供类型提示和默认值，避免参数遗漏
    - 便于序列化和日志记录
    
    业务契约：
    - sub_status 保持不变（由字幕系统独立管理）
    - season / episode 仅适用于 TV 类型
    - local_poster_path 可选（有些任务没有下载海报）
    """
    title: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    
    target_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    
    task_type: Optional[str] = None


def finalize_task(
    db,
    task_id: int,
    status: str,
    metadata: TaskFinalizationMetadata
) -> None:
    """
    统一的任务终态更新接口
    
    业务契约：
    - status 只能是终态值（archived / scraped / failed）
    - sub_status 保持不变（由字幕系统独立管理）
    - 归档流程（热表 → 冷表）由 update_task_status 内部触发
    - title / year / season 通过 update_task_title_year 更新
    - 其他元数据通过 update_task_status 更新
    
    调用顺序保证：
    1. 先更新标题和年份（update_task_title_year）
    2. 再更新状态和元数据（update_task_status）
    3. 若 status="archived"，内部触发归档流程
    
    Args:
        db: DatabaseManager 实例
        task_id: 任务 ID
        status: 终态状态（archived / scraped / failed）
        metadata: 任务元数据封装
    
    Raises:
        ValueError: 如果 status 不是终态值
    
    示例：
        >>> metadata = TaskFinalizationMetadata(
        ...     title="哪吒之魔童闹海",
        ...     year="2025",
        ...     tmdb_id=980477,
        ...     imdb_id="tt123456",
        ...     target_path="/media/movie/哪吒之魔童闹海 (2025)/...",
        ...     local_poster_path="/media/movie/哪吒之魔童闹海 (2025)/poster.jpg",
        ...     task_type="movie"
        ... )
        >>> finalize_task(db, task_id=123, status="archived", metadata=metadata)
    """
    if status not in {"archived", "scraped", "failed"}:
        raise ValueError(
            f"finalize_task 只能用于终态状态，收到: {status}。"
            f"请使用 update_task_status 更新中间状态。"
        )
    
    if metadata.title or metadata.year or metadata.season is not None:
        db.update_task_title_year(
            task_id=task_id,
            title=metadata.title,
            year=metadata.year,
            season=metadata.season,
        )
    
    db.update_task_status(
        task_id=task_id,
        status=status,
        tmdb_id=metadata.tmdb_id,
        imdb_id=metadata.imdb_id or "",
        target_path=metadata.target_path,
        local_poster_path=metadata.local_poster_path,
        task_type=metadata.task_type,
    )
    
    logger.info(
        f"[TaskFinalization] task_id={task_id}, status={status}, "
        f"title={metadata.title}, tmdb_id={metadata.tmdb_id}, "
        f"target_path={metadata.target_path}"
    )
