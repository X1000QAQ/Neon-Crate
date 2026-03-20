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
    获取任务列表（支持搜索/过滤/分页，返回前端统一 Task 契约）。

    业务链路：
    根据 status 选择数据源（tasks / media_archive / 合并去重）→ 统一字段映射（type→media_type，补 file_path）→
    路径规范化（反斜杠→正斜杠，URL 透传）→ 可选 media_type 过滤 → 返回列表与总数。

    Args:
        search: 可选。关键词搜索（后端按库内策略匹配）。
        status: 可选。状态过滤（pending/failed/archived/ignored/all...）。
        media_type: 可选。媒体类型过滤（movie/tv/all）。
        page: 可选。分页页码（当前前端主要走前端分页）。
        page_size: 可选。分页大小（前端常传大值以一次性拉全量后前端分页）。
        db: 数据库依赖注入（DbDep）。

    Returns:
        Dict[str, Any]:
            - tasks: 任务列表（已做全栈契约兜底与字段映射）
            - total: 总数
            - page: 当前页（兼容字段）
            - page_size: 返回数量

    Raises:
        HTTPException:
            - 500: 数据库读取/合并去重/字段规范化过程中出现未捕获异常。
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

        # DTO 对齐：持久层 type 映射为前端 media_type；路径字段统一 Web 正斜杠语义
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

            # 5) 阻断底层字段外泄：对外 DTO 不透出持久层字段名（type/path）
            #    仅保留映射后的 media_type/file_path
            normalized_task.pop("type", None)
            normalized_task.pop("path", None)
            normalized_task.pop("last_sub_check", None)

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
    批量删除任务记录（仅删数据库记录，不删除任何物理文件）。

    业务链路：
    接收 id 列表 → 同步删除 tasks + media_archive 双表记录 → 返回删除数量。

    Args:
        body: DeleteBatchRequest，请求体包含 `ids`（待删除的任务 ID 列表）。
        db: 数据库依赖注入（DbDep）。

    Returns:
        Dict[str, Any]:
            - success: 是否成功
            - deleted: 实际删除数量
            - message: 人类可读提示

    Raises:
        HTTPException:
            - 500: 数据库删除失败或运行时异常。
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
    销毁单条任务记录（仅删数据库记录，不删除任何物理文件）。

    业务链路：
    根据 task_id 同步删除 tasks + media_archive 双表记录（若存在）→ 返回结果。

    Args:
        task_id: 任务 ID（Path 参数）。
        db: 数据库依赖注入（DbDep）。

    Returns:
        Dict[str, Any]:
            - success: 是否成功
            - message: 人类可读提示

    Raises:
        HTTPException:
            - 404: 任务不存在或已被删除。
            - 500: 数据库删除失败或运行时异常。
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
    全量清空任务表（核弹按钮，仅删数据库记录）。

    业务链路：
    校验确认口令（CONFIRM）→ 清空 tasks 表/重置自增 → 返回清空数量。

    Body:
        payload: PurgeRequest，包含 `confirm` 字段，必须为 "CONFIRM" 才允许执行。

    Returns:
        Dict[str, Any]:
            - success: 是否成功
            - deleted: 实际删除数量
            - message: 人类可读提示

    Raises:
        HTTPException:
            - 400: confirm 口令不匹配。
            - 500: 数据库清空失败或运行时异常。
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
    重试单个任务（将状态复位为 pending，等待流水线再次处理）。

    业务链路：
    将 task_id 对应任务状态更新为 pending → 前端刷新任务列表后可被扫描/刮削流程重新拾取。

    Args:
        task_id: 任务 ID（Path 参数）。
        db: 数据库依赖注入（DbDep）。

    Returns:
        Dict[str, Any]:
            - success: 是否成功
            - message: 人类可读提示

    Raises:
        HTTPException:
            - 500: 数据库更新失败或运行时异常。
    """
    try:
        # 直接重置任务状态为 pending（不需要提前检查是否存在）
        db.update_task_status(task_id, "pending")

        logger.info(f"[API] 任务 {task_id} 已重置为 pending 状态，等待重新处理")
        return {"success": True, "message": "任务已重置，等待重新处理"}
    except Exception as e:
        logger.error(f"[API] 重试任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重试任务失败: {str(e)}")
