"""
media_router.py - 媒体库 CRUD 路由

功能说明：
- 提供媒体任务的增删改查接口
- 支持批量操作和单条操作
- 支持搜索、过滤、分页

核心接口：
1. GET /tasks - 获取所有任务列表（支持搜索、过滤、分页）
2. POST /tasks/delete_batch - 批量删除任务记录
3. DELETE /tasks/{task_id} - 单条删除任务记录
4. POST /tasks/purge - 全量清空任务表（核弹按钮）
5. POST /tasks/{task_id}/retry - 重试单个失败的任务

关键特性：

1. 双表合并查询
   - tasks 表：待处理任务（pending、failed 等）
   - media_archive 表：已归档任务（archived）
   - 自动去重：基于 path 字段去重

2. 路径格式统一
   - Windows 反斜杠 → 正斜杠
   - 在线 URL 原样透传（http://、https://）
   - 使用 Path.as_posix() 标准化

3. 媒体类型对齐
   - 数据库字段：type
   - 前端期待：media_type
   - 自动映射：type → media_type

4. 状态过滤
   - all：合并 tasks + media_archive
   - archived：仅查 media_archive
   - ignored：仅查 ignored 记录
   - 其他：按状态过滤 tasks 表

5. 安全删除
   - 仅删除数据库记录
   - 不删除物理文件
   - 支持双表删除（tasks + media_archive）
"""
import logging
from pathlib import Path
from typing import Optional, Any, Dict

from fastapi import APIRouter, HTTPException

from app.api.v1.deps import DbDep
from app.models.domain_system import DeleteBatchRequest, PurgeRequest

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_all_tasks(
    search: Optional[str] = None,
    status: Optional[str] = None,
    media_type: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
    db: DbDep = None,
):
    """
    GET /tasks - 获取所有任务列表（支持关键词搜索、状态过滤、媒体类型过滤）

    参数：
    - search: 可选，关键词匹配
    - status: 可选，状态过滤（pending/success/failed/archived/all）
    - media_type: 可选，媒体类型过滤（movie/tv）
    - page/page_size: 可选，分页（前端目前传 page_size=99999 做前端分页）

    核心修复：将数据库的 type 字段映射为前端期待的 media_type
    archived 状态从 media_archive 表读取，其余从 tasks 表读取
    """
    try:
        # 根据 status 决定查哪张表
        if status == "archived":
            # 只查 media_archive 表
            tasks = db.get_archived_data(search_keyword=search)
            for t in tasks:
                t["status"] = "archived"
        elif status == "ignored":
            # 专属查询：只返回 ignored 记录
            all_tasks = db.get_all_data(search_keyword=search, include_ignored=True)
            tasks = [t for t in all_tasks if (t.get("status") or "").lower() == "ignored"]
        elif status is None or status == "all":
            # 合并 tasks 表 + media_archive 表，并去重（严格排除 ignored）
            active_tasks = db.get_all_data(search_keyword=search, include_ignored=False)
            archived_tasks = db.get_archived_data(search_keyword=search)
            for t in archived_tasks:
                t["status"] = "archived"
            
            # 利用 path 字段进行 Set 去重
            seen_paths = set()
            tasks = []
            for t in active_tasks:
                path = t.get("path")
                if path and path not in seen_paths:
                    tasks.append(t)
                    seen_paths.add(path)
            
            for t in archived_tasks:
                path = t.get("path")
                if path and path not in seen_paths:
                    tasks.append(t)
                    seen_paths.add(path)
        else:
            # 查 tasks 表并按状态过滤（排除 ignored）
            all_tasks = db.get_all_data(search_keyword=search, include_ignored=False)
            tasks = [t for t in all_tasks if (t.get("status") or "").lower() == status.lower()]

        def _normalize_path(value: Any) -> str:
            """
            将后端内部路径统一转换为 Web 友好的格式：
            - 强制使用正斜杠 `/`
            - 保持原有盘符/前缀，仅修正分隔符
            - 对以 http:// 或 https:// 开头的在线 URL 原样透传，避免被 Path 破坏双斜杠
            """
            if not value:
                return value

            val_str = str(value)
            # 在线 URL 必须原样返回，绝对不能走 Path 解析
            if val_str.startswith("http://") or val_str.startswith("https://"):
                return val_str

            try:
                # Path.as_posix() 会自动把 Windows 反斜杠转换为正斜杠
                return Path(val_str).as_posix()
            except Exception:
                # 兜底：仅替换分隔符，避免抛异常
                return val_str.replace("\\", "/")

        # 致命修复：将数据库的 type 映射为前端期待的 media_type，并在下发前统一路径格式
        normalized_tasks = []
        for task in tasks:
            normalized_task = dict(task)

            # 1) 媒体类型对齐：type -> media_type
            media_type_value = str(normalized_task.get("type", "movie")).strip().lower()
            normalized_task["media_type"] = media_type_value

            # 2) 路径字段统一转为 Web 友好格式（正斜杠），避免出现原生 Windows `\`
            for key in ["path", "target_path", "poster_path", "local_poster_path"]:
                if key in normalized_task and normalized_task.get(key):
                    normalized_task[key] = _normalize_path(normalized_task[key])

            # 3) 兼容前端 Task 契约：补充 file_path 别名，指向原始 path
            if "file_path" not in normalized_task:
                normalized_task["file_path"] = normalized_task.get("path") or ""

            # 4) 🚀 全栈契约对齐：
            #    1. 遍历任务结果集，将数据库 NULL 值转化为前端 TypeScript 期望的非空字符串。
            #    2. 预防白屏：防止前端执行时间字符串操作（如 .substring）时因 null 抛出 TypeError。
            #    (前端 types/index.ts 将 created_at 定义为必填 string，后端 Optional[str] 需在此层兜底)
            if not normalized_task.get("created_at"):
                normalized_task["created_at"] = ""

            normalized_tasks.append(normalized_task)

        # media_type 过滤（archived 模式下也生效）
        if media_type and media_type != "all":
            normalized_tasks = [t for t in normalized_tasks if t.get("media_type") == media_type]

        logger.info(f"[API] 搜索关键词: {search!r}, 返回任务数: {len(normalized_tasks)}")
        return {
            "tasks": normalized_tasks,
            "total": len(normalized_tasks),
            "page": 1,
            "page_size": len(normalized_tasks)
        }
    except Exception as e:
        logger.error(f"[API] 获取任务列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")


@router.post("/delete_batch")
async def delete_tasks_batch(body: DeleteBatchRequest, db: DbDep = None):
    """
    POST /tasks/delete_batch - 批量删除任务记录（仅数据库，不删物理文件）
    支持删除 tasks 表和 media_archive 表中的记录
    """
    if not body.ids:
        return {"success": True, "deleted": 0, "message": "未提供任何 ID"}

    try:
        # ✅ 调用公开的 service 方法（替代直接 db._get_conn()）
        deleted = db.delete_tasks_and_archive_by_ids(body.ids)

        logger.info(f"[API] 批量删除任务 ids={body.ids}")
        return {"success": True, "deleted": deleted, "message": f"已删除 {deleted} 条记录"}
    except Exception as e:
        logger.error(f"[API] 批量删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{task_id}", summary="销毁单条任务记录")
async def delete_task_by_id(task_id: int, db: DbDep = None):
    """
    ☢️ 危险操作：从数据库中物理移除该任务。注意：此操作仅影响元数据，不会删除磁盘上的物理视频文件。
    支持删除 tasks 表和 media_archive 表中的记录
    """
    try:
        # ✅ 调用公开的 service 方法（替代直接 db._get_conn()）
        deleted = db.delete_task_and_archive_by_id(task_id)

        if not deleted:
            raise HTTPException(status_code=404, detail="任务不存在或已删除")

        logger.info(f"[API] 已删除任务 id={task_id}")
        return {"success": True, "message": "已删除该任务记录"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 删除任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge")
async def purge_all_tasks(payload: PurgeRequest, db: DbDep = None):
    """
    DELETE /tasks/purge - 全量清空 tasks 表（核弹按钮）
    仅清空数据库记录，不删物理文件

    核心功能：
    1. 清空所有任务记录
    2. 重置自增 ID 计数器
    3. 确保下次插入从 ID 1 开始
    """
    if payload.confirm.strip().upper() != "CONFIRM":
        raise HTTPException(status_code=400, detail="请正确输入 CONFIRM")

    try:
        deleted = db.clear_all_tasks()
        logger.info(f"[OK] [API] 已清空任务表，删除 {deleted} 条记录")
        return {"success": True, "deleted": deleted, "message": f"已清空 {deleted} 条任务记录"}
    except Exception as e:
        logger.error(f"[ERROR] [API] 清空任务表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/retry")
async def retry_task(task_id: int, db: DbDep = None):
    """
    POST /tasks/{task_id}/retry - 重试单个失败的任务

    功能说明：
    - 将任务状态重置为 pending
    - 清空错误信息，以便扫描引擎再次处理

    参数：
    - task_id: 任务 ID

    返回：
    - success: 是否成功
    - message: 操作结果描述
    """
    try:
        # 直接重置任务状态为 pending（不需要提前检查是否存在）
        db.update_task_status(task_id, "pending")

        logger.info(f"[API] 任务 {task_id} 已重置为 pending 状态，等待重新处理")
        return {"success": True, "message": "任务已重置，等待重新处理"}
    except Exception as e:
        logger.error(f"[API] 重试任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")
