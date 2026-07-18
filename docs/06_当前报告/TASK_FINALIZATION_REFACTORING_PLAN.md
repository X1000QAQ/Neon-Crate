# 任务终态更新逻辑统一封装 - 重构执行计划

**创建日期**：2026-06-11  
**预计工作量**：1 小时  
**优先级**：中  
**类型**：技术债务清理  

---

## 执行摘要

本计划旨在统一封装分散在多个模块中的任务状态更新逻辑，通过引入 `TaskFinalizationMetadata` 数据类和 `finalize_task()` 统一接口，提升代码一致性、降低维护成本、减少遗漏错误。

**核心目标**：
- 统一 `update_task_title_year` + `update_task_status` 的调用模式
- 封装任务终态更新的业务契约（archived / scraped / failed）
- 保持向后兼容，逐步迁移现有调用点

---

## 一、问题分析

### 1.1 当前状态更新逻辑的问题

#### 问题 1：调用顺序不一致

**场景 A：正常刮削流程**（`scrape_task.py`）

```python
db.update_task_title_year(
    task_id=task_id, title=title, year=year,
    season=season_num if refined_type == "tv" else None
)
db.update_task_status(
    task_id=task_id, status="archived",
    tmdb_id=int(tmdb_id), 
    imdb_id=imdb_id if imdb_id else "",
    target_path=target_path,
    local_poster_path=local_poster_path,
    task_type=refined_type
)
```

**场景 B：Nuclear 重构流程**（`engines.py`）

```python
self.db.update_task_title_year(
    task_id=task["id"],
    title=new_title or None,
    year=new_year or None,
    season=context.get("task_season") if media_type == "tv" else None,
)
self.db.update_task_status(
    task_id=task["id"],
    status="archived",
    tmdb_id=new_tmdb_id,
    imdb_id=new_imdb_id or "",
    target_path=new_video_path,
    local_poster_path=local_poster,
    task_type=media_type,
)
```

**问题**：
- 两处代码几乎完全重复
- 参数传递方式不一致（`int(tmdb_id)` vs `new_tmdb_id`）
- 容易遗漏某个调用（只调用 `update_task_status` 而忘记 `update_task_title_year`）

#### 问题 2：业务契约隐式

**当前逻辑**：

```python
db.update_task_status(task_id=task_id, status="archived", ...)
# 内部会触发归档流程（热表 → 冷表）
# 但这个副作用没有显式说明
```

**问题**：
- `sub_status` 的处理规则不明确（保持不变？覆盖？）
- 归档触发条件隐藏在 `update_task_status` 内部
- 新手维护者不知道哪些状态是"终态"（archived / scraped / failed）

#### 问题 3：参数列表过长

```python
self.db.update_task_status(
    task_id=task["id"],
    status="archived",
    tmdb_id=new_tmdb_id,
    imdb_id=new_imdb_id or "",
    target_path=new_video_path,
    local_poster_path=local_poster,
    task_type=media_type,
)
```

7 个参数超过了函数参数数量的推荐阈值（4-5 个）。

---

### 1.2 影响范围统计

通过代码扫描，发现以下调用点需要迁移：

| 文件 | 调用点数量 | 场景 |
|------|-----------|------|
| `scrape_task.py` | 1 | 正常刮削完成 |
| `engines.py` | 1 | Nuclear 重构完成 |
| `media_router.py` | 0 | 不直接调用 |
| `subtitle_task.py` | 0 | 只更新 `sub_status` |

**总计**：2 个主要调用点需要迁移。

---

## 二、设计方案

### 2.1 数据类设计

```python
from dataclasses import dataclass
from typing import Optional


@dataclass
class TaskFinalizationMetadata:
    """
    任务终态更新元数据封装
    
    职责：
    - 封装任务完成时需要更新的所有元数据字段
    - 提供类型提示和默认值，避免参数遗漏
    - 便于序列化和日志记录
    
    使用场景：
    - 正常刮削完成（status="archived"）
    - Nuclear 重构完成（status="archived"）
    - 刮削失败（status="failed"）
    
    业务契约：
    - sub_status 保持不变（由字幕系统独立管理）
    - season / episode 仅适用于 TV 类型
    - local_poster_path 可选（有些任务没有下载海报）
    """
    # 标题和年份信息
    title: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None  # TV 专用
    episode: Optional[int] = None  # TV 专用（保留字段，暂未使用）
    
    # 外部 ID
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    
    # 文件路径
    target_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    
    # 媒体类型
    task_type: Optional[str] = None  # movie / tv
```

---

### 2.2 统一接口设计

```python
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
    # 1. 校验状态值（防止误用）
    if status not in {"archived", "scraped", "failed"}:
        raise ValueError(
            f"finalize_task 只能用于终态状态，收到: {status}。"
            f"请使用 update_task_status 更新中间状态。"
        )
    
    # 2. 更新标题和年份（如果提供）
    if metadata.title or metadata.year or metadata.season is not None:
        db.update_task_title_year(
            task_id=task_id,
            title=metadata.title,
            year=metadata.year,
            season=metadata.season,
        )
    
    # 3. 更新状态和其他元数据
    db.update_task_status(
        task_id=task_id,
        status=status,
        tmdb_id=metadata.tmdb_id,
        imdb_id=metadata.imdb_id or "",
        target_path=metadata.target_path,
        local_poster_path=metadata.local_poster_path,
        task_type=metadata.task_type,
    )
    
    # 4. 日志记录（便于审计）
    logger.info(
        f"[TaskFinalization] task_id={task_id}, status={status}, "
        f"title={metadata.title}, tmdb_id={metadata.tmdb_id}, "
        f"target_path={metadata.target_path}"
    )
```

---

### 2.3 实现位置选择

#### 方案 A：在 `db_manager.py` 中实现

**优点**：
- 与现有 `update_task_status` 等方法在同一层级
- 便于调用（`db.finalize_task(...)`）

**缺点**：
- `db_manager.py` 已经很庞大
- 混合了业务逻辑和数据访问

#### 方案 B：在新文件 `task_finalization.py` 中实现

**优点**：
- 职责单一，便于测试
- 可以独立导入使用

**缺点**：
- 需要额外的模块导入
- 调用方式变为 `finalize_task(db, ...)`

#### 推荐方案：方案 B

创建新文件 `backend/app/services/task_finalization.py`，将数据类和函数放在其中。

**理由**：
1. 符合单一职责原则
2. 便于单元测试
3. 不污染 `db_manager.py`
4. 未来可以扩展更多任务生命周期管理功能

---

## 三、实施步骤

### 阶段一：创建新模块（10 分钟）

#### 步骤 1.1：创建 `task_finalization.py`

**文件路径**：`backend/app/services/task_finalization.py`

**内容**：包含 `TaskFinalizationMetadata` 数据类和 `finalize_task()` 函数（见"设计方案"章节）

#### 步骤 1.2：添加单元测试（可选，暂不执行）

**文件路径**：`backend/tests/test_task_finalization.py`

测试用例：
- 测试正常 archived 流程
- 测试 failed 流程
- 测试参数校验（非终态状态抛出异常）
- 测试日志记录

---

### 阶段二：迁移现有调用点（30 分钟）

#### 步骤 2.1：迁移 `scrape_task.py`

**原始代码**（约 Line 930）：

```python
db.update_task_title_year(
    task_id=task_id, title=title, year=year,
    season=season_num if refined_type == "tv" else None
)
db.update_task_status(
    task_id=task_id, status="archived",
    tmdb_id=int(tmdb_id), 
    imdb_id=imdb_id if imdb_id else "",
    target_path=target_path,
    local_poster_path=local_poster_path,
    task_type=refined_type
)
logger.info(f"[TMDB] 已校准任务 {task_id} 的媒体类型为: {refined_type}")
```

**重构后**：

```python
from app.services.task_finalization import TaskFinalizationMetadata, finalize_task

# ... 其他代码 ...

metadata = TaskFinalizationMetadata(
    title=title,
    year=year,
    season=season_num if refined_type == "tv" else None,
    tmdb_id=int(tmdb_id),
    imdb_id=imdb_id if imdb_id else "",
    target_path=target_path,
    local_poster_path=local_poster_path,
    task_type=refined_type,
)
finalize_task(db, task_id=task_id, status="archived", metadata=metadata)
logger.info(f"[TMDB] 已校准任务 {task_id} 的媒体类型为: {refined_type}")
```

#### 步骤 2.2：迁移 `engines.py`

**原始代码**（约 Line 710）：

```python
# Nuclear 重构完成后，统一调用 update_task_status 触发归档流程
# 与 AI 刮削流程对齐：status="archived"，sub_status 保持原值（通常是 pending）
if not context["is_archive"]:
    try:
        self.db.update_task_title_year(
            task_id=task["id"],
            title=new_title or None,
            year=new_year or None,
            season=context.get("task_season") if media_type == "tv" else None,
        )
        self.db.update_task_status(
            task_id=task["id"],
            status="archived",
            tmdb_id=new_tmdb_id,
            imdb_id=new_imdb_id or "",
            target_path=new_video_path,
            local_poster_path=local_poster,
            task_type=media_type,
        )
        logger.info(f"[NUCLEAR] 任务状态已更新为 archived: task_id={task['id']}")
    except Exception as e:
        logger.warning(f"[NUCLEAR] 状态更新失败（非阻断）: {e}")
```

**重构后**：

```python
from app.services.task_finalization import TaskFinalizationMetadata, finalize_task

# ... 其他代码 ...

# Nuclear 重构完成后，统一调用 finalize_task 触发归档流程
# 与 AI 刮削流程对齐：status="archived"，sub_status 保持原值（通常是 pending）
if not context["is_archive"]:
    try:
        metadata = TaskFinalizationMetadata(
            title=new_title or None,
            year=new_year or None,
            season=context.get("task_season") if media_type == "tv" else None,
            tmdb_id=new_tmdb_id,
            imdb_id=new_imdb_id or "",
            target_path=new_video_path,
            local_poster_path=local_poster,
            task_type=media_type,
        )
        finalize_task(self.db, task_id=task["id"], status="archived", metadata=metadata)
        logger.info(f"[NUCLEAR] 任务状态已更新为 archived: task_id={task['id']}")
    except Exception as e:
        logger.warning(f"[NUCLEAR] 状态更新失败（非阻断）: {e}")
```

---

### 阶段三：验证和测试（20 分钟）

#### 步骤 3.1：Linter 检查

```bash
cd backend
python -m pylint app/services/task_finalization.py
python -m pylint app/api/v1/endpoints/tasks/scrape_task.py
python -m pylint app/services/rebuilder/engines.py
```

#### 步骤 3.2：功能回归测试

**测试场景 1：正常刮削流程**

1. 扫描下载源目录 → 任务入库
2. 执行刮削 → TMDB 搜索成功
3. **验证**：
   - 任务状态变为 `archived`
   - `sub_status` 保持 `pending`
   - 标题、年份、TMDB ID、IMDb ID 正确更新
   - 海报路径正确
   - 任务已从热表移到冷表

**测试场景 2：Nuclear 重构流程**

1. 扫描下载源目录 → 任务入库
2. 刮削失败（`status=failed`）
3. 手动修改 NFO → 执行 Nuclear 重构
4. **验证**：
   - 任务状态变为 `archived`
   - `sub_status` 保持 `pending`
   - 文件硬链接到媒体库
   - NFO 和海报生成成功
   - 下载源文件保留（硬链接）
   - 下载源 NFO 保留（不被删除）

**测试场景 3：异常处理**

1. 尝试调用 `finalize_task` 并传入非终态状态（如 `status="pending"`）
2. **验证**：抛出 `ValueError` 异常

---

## 四、回滚方案

如果重构引入了问题，可以快速回滚：

### 回滚步骤

1. **删除新文件**：`backend/app/services/task_finalization.py`
2. **恢复 `scrape_task.py`**：恢复 Git 版本
3. **恢复 `engines.py`**：恢复 Git 版本
4. **重启后端**：确认功能正常

### 回滚验证

- 正常刮削流程不受影响
- Nuclear 重构流程不受影响
- 数据库状态更新正常

---

## 五、预期收益

### 5.1 代码质量提升

| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| 重复代码行数 | ~20 行 | 0 行 |
| 函数参数数量 | 7 个 | 3 个（task_id, status, metadata） |
| 调用点一致性 | 低 | 高 |
| 业务契约明确性 | 低 | 高 |
| 参数遗漏风险 | 中 | 低 |

### 5.2 可维护性提升

**重构前**：
- 修改状态更新逻辑需要同时修改 2 个文件
- 新手维护者不知道 `update_task_title_year` 和 `update_task_status` 的调用顺序
- 参数传递方式不一致，容易出错

**重构后**：
- 修改状态更新逻辑只需修改 `task_finalization.py`
- `finalize_task` 接口明确表达了"任务终态更新"的语义
- 数据类提供类型提示，减少参数遗漏

### 5.3 测试成本降低

**重构前**：
- 需要为每个调用点编写测试
- 测试用例重复

**重构后**：
- 只需为 `finalize_task` 编写测试
- 测试覆盖率提升

---

## 六、注意事项

### 6.1 向后兼容

**重要**：本次重构不删除 `update_task_status` 和 `update_task_title_year`，只是在它们之上封装了 `finalize_task`。

**原因**：
1. 有些场景只需要更新 `sub_status`（字幕系统）
2. 避免一次性修改过多代码，降低风险

### 6.2 sub_status 的处理

`finalize_task` **不会**修改 `sub_status`，保持其原有值。

**业务契约**：
- `sub_status` 由字幕系统独立管理
- 任务归档时，`sub_status` 保持 `pending`（表示字幕还没处理）
- 字幕下载完成后，字幕系统会更新 `sub_status` 为 `scraped` 或 `found`

### 6.3 数据类的扩展

如果未来需要添加新字段（如 `original_title`、`overview` 等），只需：

1. 在 `TaskFinalizationMetadata` 中添加字段
2. 在 `finalize_task` 中处理新字段
3. 不影响现有调用点

---

## 七、执行清单

### 开发阶段

- [ ] 创建 `backend/app/services/task_finalization.py`
- [ ] 实现 `TaskFinalizationMetadata` 数据类
- [ ] 实现 `finalize_task()` 函数
- [ ] 添加日志记录和异常处理
- [ ] 迁移 `scrape_task.py` 的调用点
- [ ] 迁移 `engines.py` 的调用点
- [ ] 运行 Linter 检查（Pylint）
- [ ] 修复所有 Linter 错误

### 测试阶段

- [ ] 功能测试：正常刮削流程
- [ ] 功能测试：Nuclear 重构流程
- [ ] 功能测试：异常处理（非终态状态）
- [ ] 回归测试：字幕下载流程不受影响
- [ ] 回归测试：数据库状态更新正常
- [ ] 性能测试：状态更新耗时无明显增加

### 部署阶段

- [ ] 代码审查（Code Review）
- [ ] 合并到主分支
- [ ] 部署到测试环境
- [ ] 监控日志和错误率
- [ ] 部署到生产环境

---

## 八、时间估算

| 阶段 | 任务 | 预计时间 |
|------|------|----------|
| 开发 | 创建新模块 | 10 分钟 |
| 开发 | 迁移 scrape_task.py | 10 分钟 |
| 开发 | 迁移 engines.py | 10 分钟 |
| 开发 | Linter 检查 | 5 分钟 |
| 测试 | 功能测试 | 15 分钟 |
| 测试 | 回归测试 | 10 分钟 |
| **总计** | | **60 分钟** |

---

## 九、参考资料

### 相关文档

- [CODE_QUALITY_REVIEW_2026-06-11.md](./CODE_QUALITY_REVIEW_2026-06-11.md) - 代码质量审查报告
- [task_repo.py](../../backend/app/infra/database/repositories/task_repo.py) - 任务仓储实现
- [scrape_task.py](../../backend/app/api/v1/endpoints/tasks/scrape_task.py) - 刮削流程实现
- [engines.py](../../backend/app/services/rebuilder/engines.py) - Nuclear 重构引擎实现

### 设计模式

本次重构应用了以下设计模式：

1. **数据传输对象（DTO）**：`TaskFinalizationMetadata` 封装了任务终态更新所需的所有数据
2. **门面模式（Facade）**：`finalize_task()` 为复杂的状态更新流程提供了简单的接口
3. **单一职责原则（SRP）**：新模块只负责任务终态更新逻辑

---

## 十、总结

本次重构通过引入 `TaskFinalizationMetadata` 数据类和 `finalize_task()` 统一接口，解决了任务状态更新逻辑分散、参数列表过长、业务契约不明确等问题。

**关键成功因素**：
1. 保持向后兼容，不删除现有方法
2. 逐步迁移调用点，降低风险
3. 充分测试，确保功能不受影响
4. 明确业务契约，便于后续维护

**后续优化方向**：
1. 为 `finalize_task` 添加单元测试
2. 考虑引入状态机模式，明确任务生命周期
3. 探索将 `update_any_task_metadata` 也纳入统一封装

---

**报告结束**

如需讨论具体实施细节或优先级调整，请联系开发团队。
