# 代码质量审查报告

**审查日期**：2026-06-11  
**审查范围**：Nuclear 重构引擎、AI 刮削流程、前端任务列表组件  
**审查人**：AI Agent  
**报告版本**：v1.0

---

## 执行摘要

本次审查聚焦于最近实现的 Nuclear 重构硬链接功能和 AI 置信度阈值调整，共识别出：

- **3 项技术债务**：需要优先处理的代码重复和架构问题
- **3 处代码坏味道**：影响可维护性的常见模式
- **2 个潜在风险**：可能导致数据丢失或业务异常的边界问题

总体评估：代码功能正常运行，但存在一定的维护成本和潜在风险，建议在下一个迭代周期内逐步优化。

---

## 一、技术债务（建议优先处理）

### 1.1 硬链接判断逻辑重复

**严重程度**：🔴 高  
**影响范围**：`backend/app/services/rebuilder/engines.py`  
**预计工作量**：30 分钟

#### 问题描述

Nuclear 引擎在处理 TV 单集和 Movie 电影时，重复了相同的硬链接判断和文件转移逻辑（约 15 行代码重复两次）。

#### 当前代码

TV 分支：

```python
if is_in_library:
    shutil.move(old_video_path, new_video_path)
    logger.info(f"[NUCLEAR] 媒体库内文件已移动: {old_video_path} -> {new_video_path}")
else:
    success, link_type = SmartLink.create_link(old_video_path, new_video_path)
    if not success:
        raise HTTPException(status_code=500, detail=f"[NUCLEAR] 硬链接失败: {link_type}")
    logger.info(f"[NUCLEAR] 下载源文件已硬链接入库（{link_type}）: {old_video_path} -> {new_video_path}")
```

Movie 分支：完全相同的代码块再次出现。

#### 建议方案

提取为独立方法，统一文件转移逻辑：

```python
def _transfer_video_file(
    src: str,
    dst: str,
    is_in_library: bool,
    logger
) -> bool:
    """
    统一的视频文件转移（硬链接 vs 移动）
    
    Args:
        src: 源文件路径
        dst: 目标文件路径
        is_in_library: 源文件是否在媒体库内
        logger: 日志记录器
    
    Returns:
        bool: 转移是否成功
    
    Raises:
        HTTPException: 硬链接失败时抛出
    """
    if is_in_library:
        shutil.move(src, dst)
        logger.info(f"[NUCLEAR] 媒体库内文件已移动: {src} -> {dst}")
    else:
        success, link_type = SmartLink.create_link(src, dst)
        if not success:
            raise HTTPException(
                status_code=500,
                detail=f"[NUCLEAR] 硬链接失败: {link_type}"
            )
        logger.info(
            f"[NUCLEAR] 下载源文件已硬链接入库（{link_type}）: "
            f"{src} -> {dst}"
        )
    return True
```

#### 收益分析

- **可维护性提升**：修改文件转移逻辑只需改一处
- **代码复用**：减少约 30 行重复代码
- **测试成本降低**：只需为一个方法编写单元测试

---

### 1.2 状态更新逻辑分散

**严重程度**：🟡 中  
**影响范围**：`backend/app/api/v1/endpoints/tasks/scrape_task.py`、`backend/app/services/rebuilder/engines.py`  
**预计工作量**：1 小时

#### 问题描述

任务状态更新逻辑分散在多个模块中，缺少统一的状态机封装：

- 正常刮削流程：`scrape_task.py` 调用 `update_task_status`
- Nuclear 重构流程：`engines.py` 先调用 `update_task_title_year`，再调用 `update_task_status`
- 不同场景的参数传递方式不一致

#### 建议方案

封装统一的任务终态更新方法：

```python
@dataclass
class TaskFinalizationMetadata:
    """任务终态更新元数据"""
    title: Optional[str] = None
    year: Optional[str] = None
    season: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    target_path: Optional[str] = None
    local_poster_path: Optional[str] = None
    task_type: Optional[str] = None


def finalize_task(
    db: DatabaseManager,
    task_id: int,
    status: str,
    metadata: TaskFinalizationMetadata
) -> None:
    """
    统一的任务终态更新（封装 update_task_title_year + update_task_status）
    
    业务契约：
    - status 只能是终态值（archived / scraped / failed）
    - sub_status 保持不变（由字幕系统独立管理）
    - 归档流程（热表 → 冷表）由 update_task_status 内部触发
    """
    # 更新标题和年份
    if metadata.title or metadata.year or metadata.season is not None:
        db.update_task_title_year(
            task_id=task_id,
            title=metadata.title,
            year=metadata.year,
            season=metadata.season,
        )
    
    # 更新状态和其他元数据
    db.update_task_status(
        task_id=task_id,
        status=status,
        tmdb_id=metadata.tmdb_id,
        imdb_id=metadata.imdb_id or "",
        target_path=metadata.target_path,
        local_poster_path=metadata.local_poster_path,
        task_type=metadata.task_type,
    )
```

#### 收益分析

- **一致性保证**：所有终态更新都走统一流程
- **减少遗漏**：避免忘记调用 `update_task_title_year`
- **便于审计**：状态变更日志集中记录

---

### 1.3 置信度阈值修改缺少业务注释

**严重程度**：🟢 低  
**影响范围**：`backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**预计工作量**：5 分钟

#### 问题描述

AI 识别的置信度阈值从 `0.7` 改为 `0.3`（仅警告），但没有注释说明这个决策的业务背景。未来维护者可能不理解为什么放宽阈值。

#### 当前代码

```python
if ai_confidence < 0.3:
    logger.warning(f"[AI] 置信度极低（{ai_confidence}），仍尝试 TMDB 搜索")
```

#### 建议方案

添加业务决策注释：

```python
# 用户决策（2026-06-11）：放宽置信度阈值，让 AI 尽力识别
# 
# 业务逻辑：
# - 搜不到才算真失败，不应在 AI 层提前拦截
# - 原阈值 0.7 过于严格，导致 confidence=0.85 的结果也被拒绝
# - needs_review 标记也不再阻断，交给 TMDB 验证
# 
# 当前策略：
# - confidence < 0.3: 仅记录警告，继续搜索
# - TMDB 搜索失败才标记为 failed
if ai_confidence < 0.3:
    logger.warning(
        f"[AI] 置信度极低（{ai_confidence}），仍尝试 TMDB 搜索"
    )
```

---

## 二、代码坏味道（建议逐步改进）

### 2.1 Magic Number

**严重程度**：🟢 低  
**影响范围**：`frontend/components/media/MediaTable.tsx`  
**预计工作量**：10 分钟

#### 问题描述

集数格式化函数中使用 Magic Number `2`，降低了代码的可读性和可维护性。

#### 当前代码

```typescript
function formatNumberOrUnknown(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value) 
    ? String(value).padStart(2, '0') 
    : '?';
}
```

#### 建议方案

提取为常量：

```typescript
/**
 * 剧集集数显示的位数宽度（补零到两位，如 S01E05）
 */
const EPISODE_NUMBER_WIDTH = 2;

function formatNumberOrUnknown(value: number | null | undefined) {
  return typeof value === 'number' && Number.isFinite(value)
    ? String(value).padStart(EPISODE_NUMBER_WIDTH, '0')
    : '?';
}
```

---

### 2.2 Long Parameter List

**严重程度**：🟡 中  
**影响范围**：`backend/app/services/rebuilder/engines.py`  
**预计工作量**：30 分钟

#### 问题描述

`update_task_status` 调用时传递了 7 个参数，超过了函数参数数量的推荐阈值（通常为 4-5 个）。

#### 当前代码

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

#### 建议方案

已在"技术债务 1.2"中提出的 `TaskFinalizationMetadata` 数据类可以解决这个问题。

---

### 2.3 业务链路注释过度使用

**严重程度**：🟢 低  
**影响范围**：`backend/app/services/rebuilder/engines.py`、`backend/app/services/rebuilder/rebuild_utils.py`  
**预计工作量**：30 分钟

#### 问题描述

代码中大量使用"业务链路"风格的注释，过于冗长且与代码重复。

#### 当前代码

```python
# 1. [锚定旧址] -> 2. [拔除伴生 NFO] -> 3. [释放目录回收锁]
# 1. [目录占用扫描] -> 2. [探测是否仍有其他视频存活] -> 3. [有存活则中止级联清理]
# 1. [边界锁定与核平] -> 2. [确认不越界] -> 3. [安全执行整包删除]
```

#### 建议方案

简化为单行简洁注释：

```python
# 清理旧址伴生 NFO，释放目录回收锁
# 扫描目录视频占用，有存活则中止级联清理
# 边界检查后安全删除废弃目录
```

#### 原则

- 注释应解释"为什么"，而不是复述"做什么"
- 代码本身已经清晰表达了步骤顺序
- 只在业务逻辑不直观时才添加注释

---

## 三、潜在风险（需要验证）

### 3.1 下载源 NFO 被误删

**严重程度**：🔴 高  
**风险类型**：数据丢失  
**影响范围**：`backend/app/services/rebuilder/engines.py:513`

#### 问题描述

Nuclear 重构完成硬链接后，会无条件删除 `old_video_path` 同级的 NFO 文件。当 `old_video_path` 在下载源目录时，这会破坏用户的下载源数据。

#### 风险代码

```python
# 1. [锚定旧址] -> 2. [拔除伴生 NFO] -> 3. [释放目录回收锁]
_old_path_obj = Path(old_video_path)
_old_nfo = _old_path_obj.with_suffix(".nfo")
if _old_nfo.exists():
    try:
        _old_nfo.unlink()  # 不区分是否在下载源
        logger.debug(f"[CLEANUP] 单点核爆命中旧 NFO 清除: {_old_nfo}")
    except OSError:
        pass
```

#### 触发场景

1. 用户手动修改刮削失败任务的 NFO
2. 触发 Nuclear 重构
3. 文件硬链接到媒体库成功
4. **下载源目录的 NFO 被删除**（用户可能需要保留这个文件用于 BT 客户端识别）

#### 建议方案

只在媒体库内才删除旧 NFO（保护下载源）：

```python
# 清理旧址伴生 NFO（仅媒体库内）
if is_in_library:
    _old_path_obj = Path(old_video_path)
    _old_nfo = _old_path_obj.with_suffix(".nfo")
    if _old_nfo.exists():
        try:
            _old_nfo.unlink()
            logger.debug(f"[CLEANUP] 单点核爆命中旧 NFO 清除: {_old_nfo}")
        except OSError:
            pass
else:
    logger.debug(
        f"[CLEANUP] 跳过下载源 NFO 清理，保护原始文件: "
        f"{old_video_path}"
    )
```

#### 验证方法

1. 在下载源目录放置一个带 NFO 的视频文件
2. 执行扫描 + 刮削（失败）
3. 手动修改 NFO 为正确的 TMDB ID
4. 触发 Nuclear 重构
5. **检查下载源目录的 NFO 是否仍然存在**

---

### 3.2 `_locate_video_for_task` 缺少下载源保护

**严重程度**：🟡 中  
**风险类型**：边界模糊  
**影响范围**：`backend/app/services/rebuilder/rebuild_utils.py:217`

#### 问题描述

`_locate_video_for_task` 的 Level A 逻辑直接返回 `target_path` 或 `path`，不区分文件是否在下载源。虽然当前流程中有 `is_in_library` 判断保护，但这个边界不够清晰，未来修改时可能引入风险。

#### 当前代码

```python
def _locate_video_for_task(...):
    _source_path = task_record.get("target_path") or task_record.get("path") or ""

    # Level A
    if _source_path and Path(_source_path).exists() and Path(_source_path).suffix.lower() in db_video_exts:
        logger.info(f"[NUCLEAR] 精准定位视频（source_path 直接命中）: {_source_path}")
        return _source_path  # 可能返回下载源路径
```

#### 讨论

在本次代码审查会话中，我们讨论过是否应该在 `_locate_video_for_task` 内部就拒绝返回下载源路径，但最终决定：

- **当前方案**：在上层（Nuclear 引擎）通过 `is_in_library` 判断来区分处理方式
- **理由**：`_locate_video_for_task` 的职责是"定位文件"，不应该承担"判断文件来源"的责任

这是合理的架构分层，但建议在注释中明确说明这个边界。

#### 建议方案

添加注释明确职责边界：

```python
def _locate_video_for_task(task_record: dict, db_video_exts: frozenset, search_dir: Optional[str] = None) -> Optional[str]:
    """
    四级精准定位当前任务对应的视频文件。
    
    职责边界：
    - 本函数只负责"定位文件"，不判断文件来源（下载源 vs 媒体库）
    - 调用方（如 Nuclear 引擎）需通过 is_in_library 判断来决定后续处理方式
    - Level A 可能返回下载源路径，这是预期行为
    
    Level A: target_path / path 直接存在
    Level B: inode 追踪（硬链接场景，在 search_dir 内匹配）
    Level C: file_name 精确匹配（在 search_dir 内查找）
    Level D: 三级失败 → 返回 None（由调用方决定是熔断还是跳过）
    """
```

---

## 四、优先级建议

### 高优先级（本迭代完成）

| 项目 | 类型 | 工作量 | 业务影响 |
|------|------|--------|----------|
| 3.1 下载源 NFO 被误删 | 潜在风险 | 10 分钟 | 可能导致用户数据丢失 |
| 1.1 硬链接逻辑重复 | 技术债务 | 30 分钟 | 影响后续功能迭代速度 |

### 中优先级（下迭代完成）

| 项目 | 类型 | 工作量 | 业务影响 |
|------|------|--------|----------|
| 1.2 状态更新统一封装 | 技术债务 | 1 小时 | 提升代码一致性 |
| 2.2 Long Parameter List | 代码坏味道 | 30 分钟 | 提升可读性 |
| 3.2 下载源保护边界模糊 | 潜在风险 | 10 分钟 | 预防未来误操作 |

### 低优先级（技术债务清理周期）

| 项目 | 类型 | 工作量 | 业务影响 |
|------|------|--------|----------|
| 1.3 置信度阈值注释 | 技术债务 | 5 分钟 | 改善代码可维护性 |
| 2.1 Magic Number | 代码坏味道 | 10 分钟 | 轻微影响可读性 |
| 2.3 注释简化 | 代码坏味道 | 30 分钟 | 改善代码美观度 |

---

## 五、代码审查清单

在实施上述建议后，请逐项检查：

### 功能验证

- [ ] 下载源文件的 NFO 不会被 Nuclear 重构删除
- [ ] 硬链接和移动逻辑在 TV 和 Movie 场景下行为一致
- [ ] 任务状态更新在所有场景下符合预期（archived + pending）

### 代码质量

- [ ] 没有重复的硬链接判断逻辑
- [ ] 状态更新走统一的 `finalize_task` 方法
- [ ] Magic Number 已提取为常量
- [ ] 业务决策有清晰的注释说明

### 回归测试

- [ ] 正常刮削流程不受影响
- [ ] Nuclear 重构（媒体库内文件）正常工作
- [ ] Nuclear 重构（下载源文件）正常工作且不破坏源文件
- [ ] 任务列表前端显示正确（已归档 + 排队中）

---

## 六、总结

本次代码审查识别的问题主要集中在 **Nuclear 重构引擎** 的硬链接功能实现上，核心问题是：

1. **边界模糊**：下载源和媒体库的处理逻辑没有完全隔离
2. **代码重复**：相同的硬链接判断逻辑出现两次
3. **缺少注释**：业务决策（如置信度阈值放宽）缺少上下文说明

这些问题不会影响系统的正常运行，但会增加后续维护成本，建议在下一个迭代周期内逐步优化。

**特别提醒**：3.1 下载源 NFO 被误删是高风险问题，建议优先修复。

---

**报告结束**

如需讨论具体实施方案或优先级调整，请联系开发团队。
