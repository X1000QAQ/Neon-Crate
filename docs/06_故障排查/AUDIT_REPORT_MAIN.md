# 🚨 全栈逻辑死岔路与黑洞审计报告

**文档编号**：AUDIT-001  
**日期**：2026-03-16  
**状态**：⚠️ 发现 7 个致命漏洞  
**审计范围**：RebuildDialog.tsx, MediaTable.tsx, api.ts, scrape_task.py, task_repo.py

---

## 📋 执行摘要

本审计通过**静态控制流分析**（Static Control Flow Analysis），对 Neon-Crate 系统的核心业务链路进行了深度扫雷。发现了 **7 个致命逻辑漏洞**，其中 **3 个为 CRITICAL 级别**。

### 最危险的 3 个漏洞

| 编号 | 漏洞 | 风险 | 后果 |
|------|------|------|------|
| **2.1** | _scrape_entry_lock 泄漏 | 🔴 CRITICAL | 系统永久僵死 |
| **7.1** | 就地补录缺 continue | 🔴 CRITICAL | 文件被错误移动 |
| **3.1** | 归档触发在锁外 | 🔴 HIGH | 数据不一致 |

---

## 🎯 漏洞总览表

| 编号 | 防线 | 漏洞名称 | 风险 | 触发条件 |
|------|------|---------|------|----------|
| 1.1 | 前端状态黑洞 | RebuildDialog 按钮永久僵死 | 🔴 HIGH | onConfirm 抛异常 |
| 1.2 | 前端状态黑洞 | MediaTable 静默失败 | 🟡 MEDIUM | 父组件吞掉异常 |
| **2.1** | 后端并发死锁 | _scrape_entry_lock 泄漏 | 🔴 **CRITICAL** | BaseException 中断 |
| 2.2 | 后端并发死锁 | continue 跳过计数 | 🟢 LOW | 存量库字幕检测 |
| 3.1 | 数据库事务孤儿 | 归档触发在锁外 | 🔴 HIGH | archive_task 失败 |
| 6.1 | 数据库竞态条件 | 双表查询无事务 | 🟡 MEDIUM | 并发归档 |
| **7.1** | 控制流死岔路 | 就地补录缺 continue | 🔴 **CRITICAL** | pending 任务在 library |

---

## 防线 1：前端状态黑洞

### 漏洞 1.1 - RebuildDialog 按钮永久僵死

**位置**：`frontend/components/media/RebuildDialog.tsx:217-229`

**问题**：
```typescript
const handleNuclearExecute = () => {
  if (executing) return;
  setExecuting(true);
  onConfirm({...});  // ❌ 若抛异常，setExecuting(false) 永不执行
  onClose();
};
```

**后果**：
- 若 `onConfirm()` 抛异常（网络错误、后端 500），`executing` 被冻结在 `true`
- 按钮永久 disabled，用户无法再次点击
- 系统陷入死局

**修复**：添加 try-catch-finally
```typescript
const handleNuclearExecute = async () => {
  if (executing) return;
  setExecuting(true);
  try {
    await onConfirm({...});
    onClose();
  } catch (err) {
    console.error('[REBUILD] 失败:', err);
  } finally {
    setExecuting(false);  // ✅ 无论成功失败都恢复
  }
};
```

---

### 漏洞 1.2 - MediaTable 静默失败

**位置**：`frontend/components/media/MediaTable.tsx:395-408`

**问题**：
```typescript
const handleRebuildConfirm = useCallback(async (params) => {
  setRebuildingId(dialogTask.id);
  try {
    await onRebuild({...});
  } finally {
    setRebuildingId(null);  // ❌ 异常被吞掉，用户看不到错误
  }
}, [...]);
```

**后果**：
- 若 `onRebuild()` 失败，异常被吞掉
- 用户看不到任何错误提示
- 按钮恢复正常，用户以为成功，但实际失败

**修复**：添加 catch 块显示错误
```typescript
try {
  await onRebuild({...});
  toast.success('补录成功');
} catch (err) {
  toast.error(`补录失败: ${(err as Error).message}`);
} finally {
  setRebuildingId(null);
}
```

---

## 防线 2：后端并发死锁

### 漏洞 2.1 - _scrape_entry_lock 泄漏 ⚠️ CRITICAL

**位置**：`backend/app/api/v1/endpoints/tasks/scrape_task.py:82-86`

**问题**：
```python
finally:
    scrape_all_status["is_running"] = False
    _scrape_entry_lock.release()  # ❌ BaseException 时可能不执行
```

**后果**：
- 若遇到 `MemoryError`、`KeyboardInterrupt` 等 `BaseException`
- Python 解释器可能在 `finally` 前就被强制终止
- 锁永久占用，系统无法自愈
- 下次请求被永久拦截，系统僵死

**修复**：使用 acquired 标志
```python
acquired = False
try:
    acquired = _scrape_entry_lock.acquire(blocking=False)
    if not acquired:
        return
    # ... 执行任务 ...
except BaseException as e:
    logger.error(f"[SCRAPE] 严重中断: {e}", exc_info=True)
    raise
finally:
    scrape_all_status["is_running"] = False
    if acquired:
        _scrape_entry_lock.release()  # ✅ 只释放已获取的锁
```

---

### 漏洞 2.2 - continue 跳过计数

**位置**：`backend/app/api/v1/endpoints/tasks/scrape_task.py:195-207`

**问题**：
```python
if _check_local_subtitles(_sub_path):
    db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
    processed += 1
    continue  # ❌ 没有 success_count += 1
```

**后果**：
- 统计信息不准：`success_count + failed_count < processed`
- 用户看到的统计数据与实际不符

**修复**：添加 success_count
```python
if _check_local_subtitles(_sub_path):
    db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
    success_count += 1  # ✅ 添加这一行
    processed += 1
    continue
```

---

## 防线 3：数据库事务孤儿

### 漏洞 3.1 - 归档触发在锁外

**位置**：`backend/app/infra/database/repositories/task_repo.py:180-197`

**问题**：
```python
with self.db_lock:
    conn.execute("UPDATE tasks SET status='archived' WHERE id=?", ...)
    conn.commit()  # ✅ 在锁内提交

# ❌ 归档触发在锁外
if status == "archived":
    _ar.archive_task(task_id)  # 若失败，热表已变 archived，冷表无记录
```

**后果**：
- 热表任务状态已变为 `archived`
- 但若 `archive_task()` 失败，冷表 `media_archive` 中**没有对应记录**
- 数据不一致，任务变成"幽灵归档"

**修复**：归档触发在锁内执行
```python
with self.db_lock:
    conn.execute("UPDATE tasks SET status='archived' WHERE id=?", ...)
    conn.commit()
    
    # ✅ 归档触发在锁内执行
    if status == "archived":
        _ar.archive_task(task_id)
```

---

## 防线 6：数据库竞态条件

### 漏洞 6.1 - 双表查询无事务

**位置**：`backend/app/infra/database/repositories/task_repo.py:118-177`

**问题**：
```python
with self.db_lock:
    conn = self._get_conn()
    # ❌ 没有 BEGIN 事务
    cursor = conn.execute("SELECT ... FROM tasks WHERE ...")
    rows = cursor.fetchall()
    # ❌ 两次查询之间没有事务保护
    cursor2 = conn.execute("SELECT ... FROM media_archive WHERE ...")
```

**后果**：
- 两次查询之间，另一个线程可能执行 `archive_task()`
- 任务从热表移到冷表
- 两次查询都返回该任务，导致**重复处理**

**修复**：使用事务
```python
with self.db_lock:
    conn = self._get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")  # ✅ 开启事务
        cursor = conn.execute("SELECT ... FROM tasks WHERE ...")
        rows = cursor.fetchall()
        cursor2 = conn.execute("SELECT ... FROM media_archive WHERE ...")
        conn.commit()  # ✅ 提交事务
    except Exception as e:
        conn.rollback()
        raise
```

---

## 防线 7：控制流死岔路

### 漏洞 7.1 - 就地补录缺 continue ⚠️ CRITICAL

**位置**：`backend/app/api/v1/endpoints/tasks/scrape_task.py:330-398`

**问题**：
```python
if _is_library_file:
    # 就地补录模式
    # ... 写入 NFO 和海报 ...
    
    if task.get("status") == "archived":
        db.update_any_task_metadata(...)
        success_count += 1
        processed += 1
        continue  # ✅ 这里有 continue
    # ❌ 但若 status != 'archived'，没有 continue
else:
    # 归档全链路
    SmartLink.create_link(file_path, target_path)  # ❌ 文件被错误移动
```

**后果**：
- 若 `_is_library_file=True` 且 `task.status='pending'`
- 进入就地补录块，写入 NFO 和海报
- **没有 continue**，继续执行 else 块
- 文件被**错误移动**到媒体库
- 原始位置的文件丢失

**修复**：无论 status 是什么都要 continue
```python
if _is_library_file:
    # 就地补录模式
    # ... 写入 NFO 和海报 ...
    
    # ✅ 无论 status 是什么，都要更新元数据并 continue
    db.update_any_task_metadata(task_id, _is_arc, ...)
    success_count += 1
    processed += 1
    continue  # ✅ 必须 continue，防止进入 else 块
else:
    # 归档全链路
    # ...
```

---

## 🔧 修复优先级

### 🔴 CRITICAL（立即修复）
- **2.1** - _scrape_entry_lock 泄漏（系统僵死）
- **7.1** - 就地补录缺 continue（文件丢失）

### 🔴 HIGH（尽快修复）
- **1.1** - RebuildDialog 按钮僵死
- **3.1** - 归档触发在锁外

### 🟡 MEDIUM（应该修复）
- **1.2** - MediaTable 静默失败
- **6.1** - 双表查询无事务

### 🟢 LOW（可以修复）
- **2.2** - continue 跳过计数

---

## ✅ 验证清单

修复后需要验证：

- [ ] 前端：RebuildDialog 在网络错误时能正确恢复按钮状态
- [ ] 前端：MediaTable 补录失败时显示错误提示
- [ ] 后端：_scrape_entry_lock 在异常时被正确释放
- [ ] 后端：就地补录任务不会被移动到错误位置
- [ ] 数据库：归档任务在热表和冷表中数据一致
- [ ] 数据库：并发归档不会导致任务重复处理
- [ ] 统计：success_count + failed_count = processed

---

**审计完成日期**：2026-03-16  
**审计人员**：Architecture Audit Team  
**下一步**：实施修复并进行回归测试
