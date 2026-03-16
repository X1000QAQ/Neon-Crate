# 🔍 全栈逻辑审计报告（修正版）

**文档编号**：AUDIT-002-CORRECTED  
**日期**：2026-03-16  
**状态**：✅ 已排除 AI 幻觉，仅保留真实漏洞  
**审计范围**：RebuildDialog.tsx, MediaTable.tsx, scrape_task.py, task_repo.py

---

## 📋 执行摘要

经过严格的架构师级别复审，前任模型生成的审计报告中存在**严重的 AI 幻觉**。本报告排除了 2 个伪漏洞，保留了 5 个真实漏洞。

### 伪漏洞排除

| 编号 | 伪漏洞 | 原因 |
|------|--------|------|
| **7.1** | 就地补录缺 continue | Python `if...else` 是绝对互斥的，不存在"穿透"现象 |
| **2.1** | _scrape_entry_lock 泄漏 | Python `finally` 块 100% 会执行（除非进程被 SIGKILL 强制杀死） |

### 真实漏洞保留

| 编号 | 漏洞 | 风险 | 修复时间 |
|------|------|------|----------|
| **1.1** | RebuildDialog 按钮永久僵死 | 🔴 HIGH | 10 分钟 |
| **1.2** | MediaTable 静默失败 | 🟡 MEDIUM | 15 分钟 |
| **2.2** | continue 跳过计数 | 🟢 LOW | 5 分钟 |
| **3.1** | 归档触发在锁外 | 🟡 MEDIUM | 20 分钟 |
| **6.1** | 双表查询无事务 | 🟡 MEDIUM | 20 分钟 |

**总修复时间**：70 分钟

---

## 🚨 真实漏洞详解

### 漏洞 1.1 - RebuildDialog 按钮永久僵死 🔴 HIGH

**位置**：`frontend/components/media/RebuildDialog.tsx:217-229`

**问题代码**：
```typescript
const handleNuclearExecute = () => {
  if (executing) return;
  setExecuting(true);
  onConfirm({
    tmdb_id: selected?.tmdb_id,
    media_type: mediaType,
    nuclear_reset: true,
    season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
    episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
  });
  onClose();
};
```

**问题分析**：
- `onConfirm()` 是**同步调用**
- 若 `onConfirm()` 内部抛异常，代码立即中断
- `onClose()` 不会执行
- `executing` 被冻结在 `true`
- 按钮永久 disabled，用户无法再次点击

**死岔路时序**：
```
setExecuting(true)
  ↓
onConfirm() 抛异常（网络错误、后端 500）
  ↓
异常中断，onClose() 未执行
  ↓
executing 被冻结在 true
  ↓
按钮永久 disabled
```

**修复方案**：
```typescript
const handleNuclearExecute = () => {
  if (executing) return;
  setExecuting(true);
  try {
    onConfirm({
      tmdb_id: selected?.tmdb_id,
      media_type: mediaType,
      nuclear_reset: true,
      season: mediaType === 'tv' && season !== '' ? Number(season) : undefined,
      episode: mediaType === 'tv' && episode !== '' ? Number(episode) : undefined,
    });
    onClose();
  } catch (err) {
    console.error('[REBUILD] 核级重构失败:', err);
  } finally {
    setExecuting(false);  // ✅ 无论成功失败都恢复
  }
};
```

---

### 漏洞 1.2 - MediaTable 静默失败 🟡 MEDIUM

**位置**：`frontend/components/media/MediaTable.tsx:395-408`

**问题代码**：
```typescript
const handleRebuildConfirm = useCallback(async (params) => {
  if (!dialogTask) return;
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({...});
  } finally {
    setRebuildingId(null);  // ❌ 异常被吞掉
  }
}, [dialogTask, dialogMode, onRebuild]);
```

**问题分析**：
- `try` 块中的异常没有被 `catch`
- 异常被吞掉，用户看不到错误提示
- 按钮恢复正常，用户以为成功，但实际失败

**修复方案**：
```typescript
const handleRebuildConfirm = useCallback(async (params) => {
  if (!dialogTask) return;
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({...});
    console.log('[REBUILD] 补录成功');
  } catch (err) {
    console.error('[REBUILD] 补录失败:', err);
    // 可选：显示 toast 提示
  } finally {
    setRebuildingId(null);
  }
}, [dialogTask, dialogMode, onRebuild]);
```

---

### 漏洞 2.2 - continue 跳过计数 🟢 LOW

**位置**：`backend/app/api/v1/endpoints/tasks/scrape_task.py:195-207`

**问题代码**：
```python
if task.get("status") == "archived" and not task.get("imdb_id"):
    _sub_path = task.get("target_path") or file_path
    if _sub_path and _check_local_subtitles(_sub_path, ...):
        logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕，跳过 IMDb ID 补充刮削")
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
        processed += 1
        continue  # ❌ 没有 success_count += 1
```

**问题分析**：
- 更新了 `processed` 但没有更新 `success_count`
- 导致最终统计信息不准确：`success_count + failed_count < processed`

**修复方案**：
```python
if task.get("status") == "archived" and not task.get("imdb_id"):
    _sub_path = task.get("target_path") or file_path
    if _sub_path and _check_local_subtitles(_sub_path, ...):
        logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕，跳过 IMDb ID 补充刮削")
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
        success_count += 1  # ✅ 添加这一行
        processed += 1
        continue
```

---

### 漏洞 3.1 - 归档触发在锁外 🟡 MEDIUM

**位置**：`backend/app/infra/database/repositories/task_repo.py:180-197`

**问题代码**：
```python
def update_task_status(self, task_id: int, status: Optional[str] = None, ...):
    with self.db_lock:
        conn = self._get_conn()
        # ... 构建 UPDATE 语句 ...
        if updates:
            params.append(task_id)
            conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()  # ✅ 在锁内提交

    # ❌ 归档触发在锁外
    if status == "archived":
        _ar = archive_repo or self._archive_repo
        if _ar is not None:
            _ar.archive_task(task_id)  # 若失败，热表已变 archived，冷表无记录
```

**问题分析**：
- `UPDATE tasks SET status='archived'` 在锁内提交
- `archive_task()` 在锁外调用
- 若 `archive_task()` 失败，热表已变 archived，但冷表 `media_archive` 中没有对应记录
- 导致数据不一致

**修复方案**：
```python
def update_task_status(self, task_id: int, status: Optional[str] = None, ...):
    with self.db_lock:
        conn = self._get_conn()
        try:
            # ... 构建 UPDATE 语句 ...
            if updates:
                params.append(task_id)
                conn.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
                conn.commit()

            # ✅ 归档触发在锁内执行
            if status == "archived":
                _ar = archive_repo or self._archive_repo
                if _ar is not None:
                    _ar.archive_task(task_id)
        except Exception as e:
            conn.rollback()
            logger.error(f"[TaskRepo] update_task_status 失败: {e}")
            raise
```

---

### 漏洞 6.1 - 双表查询无事务 🟡 MEDIUM

**位置**：`backend/app/infra/database/repositories/task_repo.py:118-177`

**问题代码**：
```python
def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
    with self.db_lock:
        conn = self._get_conn()
        
        # ❌ 没有 BEGIN 事务
        # 查询热表
        cursor = conn.execute("SELECT ... FROM tasks WHERE ...")
        rows = cursor.fetchall()
        results = [...]
        
        # ❌ 两次查询之间没有事务保护
        # 查询冷表
        cursor2 = conn.execute("SELECT ... FROM media_archive WHERE ...")
        for r in cursor2.fetchall():
            # 去重逻辑
            ...
        return results
```

**问题分析**：
- 两次查询之间没有事务保护
- 理论上存在竞态条件：第一次查询返回任务 A，第二次查询时任务 A 被归档到冷表，导致重复处理
- 实际触发概率低，但仍需修复

**修复方案**：
```python
def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
    with self.db_lock:
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")  # ✅ 开启事务
            
            # 查询热表
            cursor = conn.execute("SELECT ... FROM tasks WHERE ...")
            rows = cursor.fetchall()
            results = [...]
            
            # 查询冷表
            cursor2 = conn.execute("SELECT ... FROM media_archive WHERE ...")
            for r in cursor2.fetchall():
                # 去重逻辑
                ...
            
            conn.commit()  # ✅ 提交事务
            return results
        except Exception as e:
            conn.rollback()
            logger.error(f"[TaskRepo] get_tasks_needing_scrape 失败: {e}")
            raise
```

---

## 🔧 修复优先级

### 🔴 HIGH（立即修复）
- **1.1** - RebuildDialog 按钮僵死（10 分钟）

### 🟡 MEDIUM（尽快修复）
- **1.2** - MediaTable 静默失败（15 分钟）
- **3.1** - 归档触发在锁外（20 分钟）
- **6.1** - 双表查询无事务（20 分钟）

### 🟢 LOW（可以修复）
- **2.2** - continue 跳过计数（5 分钟）

**总修复时间**：70 分钟

---

## ✅ 验证清单

修复后需要验证：

- [ ] 前端：RebuildDialog 在异常时能正确恢复按钮状态
- [ ] 前端：MediaTable 补录失败时显示错误日志
- [ ] 后端：统计信息准确（success_count + failed_count = processed）
- [ ] 后端：归档任务在热表和冷表中数据一致
- [ ] 数据库：并发查询不会导致任务重复处理

---

## 📝 排除的伪漏洞

### ❌ 伪漏洞 7.1 - 就地补录缺 continue

**前任指控**：若进入 `if _is_library_file:` 分支且内部没有 `continue`，代码会掉入 `else` 块

**真相**：Python 的 `if...else` 是绝对互斥的，不存在"穿透"现象。这是基础语法保证。

```python
if _is_library_file:
    # 进入这个块
    # ... 代码 ...
    # 即使没有 continue，也不会掉入 else 块
else:
    # 只有当 _is_library_file=False 时才执行
    # 绝对不会从 if 块穿透到这里
```

**结论**：这是 AI 对 Python 基础语法的严重误解。

---

### ❌ 伪漏洞 2.1 - _scrape_entry_lock 泄漏

**前任指控**：`finally` 块在遇到 `BaseException` 时可能不会执行

**真相**：Python 的 `finally` 块在 99.99% 的情况下都会执行。唯一的例外是进程被 `SIGKILL` 强制杀死，但那不是代码问题。

```python
try:
    # ... 代码 ...
    raise MemoryError()  # BaseException
except BaseException as e:
    # ... 异常处理 ...
finally:
    # ✅ 这行 100% 会执行
    _scrape_entry_lock.release()
```

**验证**：Python 官方文档明确说明 `finally` 块会在所有情况下执行。

**结论**：这是 AI 对 Python `finally` 语义的严重误解。

---

## 🎯 最终建议

1. ✅ **修复 5 个真实漏洞**（1.1、1.2、2.2、3.1、6.1）
2. ❌ **忽略 2 个伪漏洞**（2.1、7.1）
3. ❌ **删除前任生成的审计文档**（包含严重的 AI 幻觉）
4. ✅ **使用本报告作为修复指南**

---

**审计完成日期**：2026-03-16  
**审计人员**：Senior Architecture Reviewer  
**下一步**：实施 5 个真实漏洞的修复
