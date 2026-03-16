# 后端修复方案 (AUDIT_FIXES_BACKEND.md)

## 漏洞 2.1 - _scrape_entry_lock 泄漏 ⚠️ CRITICAL

### 修复前代码
```python
def perform_scrape_all_task_sync():
    if not _scrape_entry_lock.acquire(blocking=False):
        logger.warning("[SCRAPE] ⚠️ 拦截并发请求")
        return

    global scrape_all_status

    try:
        # ... 执行刮削任务 ...
        pass
    except Exception as e:
        scrape_all_status["error"] = str(e)
        logger.error(f"[TMDB] 全量刮削执行失败: {str(e)}")
        # ... 异常处理 ...
    finally:
        scrape_all_status["is_running"] = False
        _scrape_entry_lock.release()  # ❌ BaseException 时可能不执行
```

### 修复后代码
```python
def perform_scrape_all_task_sync():
    acquired = False  # ✅ 添加标志
    try:
        acquired = _scrape_entry_lock.acquire(blocking=False)
        if not acquired:
            logger.warning("[SCRAPE] ⚠️ 拦截并发请求：已有刮削任务正在运行中，本次触发已丢弃。")
            return

        global scrape_all_status

        if scrape_all_status["is_running"]:
            return

        scrape_all_status["is_running"] = True
        scrape_all_status["error"] = None

        logger.info("[TMDB] 开始全量刮削任务（线程池模式）...")

        # ... 执行刮削任务 ...
        
    except BaseException as e:  # ✅ 捕获所有异常
        scrape_all_status["error"] = str(e)
        logger.error(f"[TMDB] 全量刮削执行失败: {str(e)}", exc_info=True)
        # ... 异常处理 ...
        raise  # ✅ 重新抛出异常
    finally:
        scrape_all_status["is_running"] = False
        if acquired:  # ✅ 只释放已获取的锁
            _scrape_entry_lock.release()
```

### 关键改动
1. 添加 `acquired` 标志记录是否成功获取锁
2. 改为捕获 `BaseException` 而不是 `Exception`
3. 在 `finally` 块中检查 `acquired` 标志
4. 只释放已获取的锁

---

## 漏洞 2.2 - continue 跳过计数

### 修复前代码
```python
# 位置：195-207 行
if task.get("status") == "archived" and not task.get("imdb_id"):
    _sub_path = task.get("target_path") or file_path
    if _sub_path and _check_local_subtitles(_sub_path, sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))):
        logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕，跳过 IMDb ID 补充刮削，节省 Token -> {_sub_path}")
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
        processed += 1
        continue  # ❌ 没有 success_count += 1
```

### 修复后代码
```python
# 位置：195-207 行
if task.get("status") == "archived" and not task.get("imdb_id"):
    _sub_path = task.get("target_path") or file_path
    if _sub_path and _check_local_subtitles(_sub_path, sub_exts=_parse_sub_exts(db.get_config("supported_subtitle_exts", ""))):
        logger.info(f"[SCRAPE] 🎯 存量库本地已有字幕，跳过 IMDb ID 补充刮削，节省 Token -> {_sub_path}")
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(task_id, _is_arc, sub_status="success")
        success_count += 1  # ✅ 添加这一行
        processed += 1
        continue
```

### 关键改动
1. 添加 `success_count += 1`

---

## 漏洞 3.1 - 归档触发在锁外

### 修复前代码
```python
def update_task_status(
    self,
    task_id: int,
    status: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
    target_path: Optional[str] = None,
    sub_status: Optional[str] = None,
    last_sub_check: Optional[str] = None,
    local_poster_path: Optional[str] = None,
    task_type: Optional[str] = None,
    archive_repo=None,
):
    with self.db_lock:
        conn = self._get_conn()
        updates = []
        params = []
        if status is not None:
            updates.append("status = ?"); params.append(status)
        # ... 其他字段 ...
        if updates:
            params.append(task_id)
            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
            )
            conn.commit()

    # ❌ 归档触发在锁外执行
    if status == "archived":
        _ar = archive_repo or self._archive_repo
        if _ar is not None:
            _ar.archive_task(task_id)  # 若失败，热表已变 archived，冷表无记录
        else:
            logger.warning(
                f"[TaskRepo] update_task_status: status=archived 但 archive_repo 未注入，"
                f"task_id={task_id} 跳过归档。请检查 DatabaseManager 初始化顺序。"
            )
```

### 修复后代码
```python
def update_task_status(
    self,
    task_id: int,
    status: Optional[str] = None,
    tmdb_id: Optional[str] = None,
    imdb_id: Optional[str] = None,
    target_path: Optional[str] = None,
    sub_status: Optional[str] = None,
    last_sub_check: Optional[str] = None,
    local_poster_path: Optional[str] = None,
    task_type: Optional[str] = None,
    archive_repo=None,
):
    with self.db_lock:
        conn = self._get_conn()
        try:
            updates = []
            params = []
            if status is not None:
                updates.append("status = ?"); params.append(status)
            # ... 其他字段 ...
            if updates:
                params.append(task_id)
                conn.execute(
                    f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params
                )
                conn.commit()

            # ✅ 归档触发在锁内执行
            if status == "archived":
                _ar = archive_repo or self._archive_repo
                if _ar is not None:
                    _ar.archive_task(task_id)  # ✅ 在锁内执行，确保原子性
                else:
                    logger.warning(
                        f"[TaskRepo] update_task_status: status=archived 但 archive_repo 未注入，"
                        f"task_id={task_id} 跳过归档。请检查 DatabaseManager 初始化顺序。"
                    )
        except Exception as e:
            conn.rollback()
            logger.error(f"[TaskRepo] update_task_status 失败: {e}", exc_info=True)
            raise
```

### 关键改动
1. 将 `archive_task()` 调用移到 `with self.db_lock:` 块内
2. 添加 `try-except-rollback` 保护
3. 确保原子性：要么都成功，要么都失败

---

## 漏洞 6.1 - 双表查询无事务

### 修复前代码
```python
def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
    with self.db_lock:
        conn = self._get_conn()
        
        # ❌ 没有 BEGIN 事务
        # 查询热表
        cursor = conn.execute(
            """
            SELECT id, path, file_name, clean_name, type, status, season, episode,
                   imdb_id, tmdb_id, target_path, sub_status, 0 as is_archive
            FROM tasks
            WHERE status = 'pending'
               OR (status = 'archived'
                   AND (imdb_id IS NULL OR imdb_id = '')
                   AND (sub_status IS NULL OR sub_status != 'success'))
            ORDER BY created_at ASC
            """
        )
        rows = cursor.fetchall()
        results = [...]
        
        # ❌ 两次查询之间没有事务保护
        # 查询冷表
        cursor2 = conn.execute(
            """
            SELECT original_task_id AS id, path, file_name, '' as clean_name, type, 'archived' as status,
                   NULL as season, NULL as episode,
                   imdb_id, tmdb_id, target_path, sub_status, 1 as is_archive
            FROM media_archive
            WHERE (imdb_id IS NULL OR imdb_id = '')
              AND (sub_status IS NULL OR sub_status != 'success')
              AND (target_path IS NOT NULL AND target_path != '')
            ORDER BY archived_at ASC
            """
        )
        for r in cursor2.fetchall():
            # 去重逻辑
            ...
        return results
```

### 修复后代码
```python
def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
    with self.db_lock:
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")  # ✅ 开启事务
            
            # 查询热表
            cursor = conn.execute(
                """
                SELECT id, path, file_name, clean_name, type, status, season, episode,
                       imdb_id, tmdb_id, target_path, sub_status, 0 as is_archive
                FROM tasks
                WHERE status = 'pending'
                   OR (status = 'archived'
                       AND (imdb_id IS NULL OR imdb_id = '')
                       AND (sub_status IS NULL OR sub_status != 'success'))
                ORDER BY created_at ASC
                """
            )
            rows = cursor.fetchall()
            results = [...]
            
            # 查询冷表
            cursor2 = conn.execute(
                """
                SELECT original_task_id AS id, path, file_name, '' as clean_name, type, 'archived' as status,
                       NULL as season, NULL as episode,
                       imdb_id, tmdb_id, target_path, sub_status, 1 as is_archive
                FROM media_archive
                WHERE (imdb_id IS NULL OR imdb_id = '')
                  AND (sub_status IS NULL OR sub_status != 'success')
                  AND (target_path IS NOT NULL AND target_path != '')
                ORDER BY archived_at ASC
                """
            )
            for r in cursor2.fetchall():
                # 去重逻辑
                ...
            
            conn.commit()  # ✅ 提交事务
            return results
        except Exception as e:
            conn.rollback()
            logger.error(f"[TaskRepo] get_tasks_needing_scrape 失败: {e}", exc_info=True)
            raise
```

### 关键改动
1. 添加 `conn.execute("BEGIN IMMEDIATE")`
2. 在两次查询后添加 `conn.commit()`
3. 添加 `try-except-rollback` 保护

---

## 漏洞 7.1 - 就地补录缺 continue ⚠️ CRITICAL

### 修复前代码
```python
# 位置：330-398 行
if _is_library_file:
    # 就地补录模式
    logger.info(f"[ORG] 就地补录模式：文件来自 library 路径或已归档，仅更新元数据")
    metadata_dir = os.path.dirname(task_file_path)
    
    # ... 写入 NFO 和海报 ...
    
    if task.get("status") == "archived":
        # 存量文件轻量级更新
        logger.info(f"[ORG] 存量库文件已补齐 IMDb ID: {imdb_id}，更新元数据即可")
        _is_arc = task.get("is_archive", False)
        db.update_any_task_metadata(
            task_id, _is_arc,
            imdb_id=imdb_id if imdb_id else None,
            tmdb_id=str(tmdb_id) if tmdb_id else None,
            sub_status="pending",
            title=title,
            year=year
        )
        success_count += 1
        processed += 1
        continue  # ✅ 这里有 continue
    # ❌ 但若 status != 'archived'，没有 continue，会继续执行下面的代码
else:
    # 归档全链路
    library_root = db.get_active_library_path(refined_type)
    # ... 移动文件 ...
    SmartLink.create_link(file_path, target_path)  # ❌ 文件被错误移动
```

### 修复后代码
```python
# 位置：330-398 行
if _is_library_file:
    # 就地补录模式
    logger.info(f"[ORG] 就地补录模式：文件来自 library 路径或已归档，仅更新元数据")
    metadata_dir = os.path.dirname(task_file_path)
    
    # ... 写入 NFO 和海报 ...
    
    # ✅ 无论 status 是什么，都要更新元数据并 continue
    _is_arc = task.get("is_archive", False)
    db.update_any_task_metadata(
        task_id, _is_arc,
        imdb_id=imdb_id if imdb_id else None,
        tmdb_id=str(tmdb_id) if tmdb_id else None,
        sub_status="pending",
        title=title,
        year=year
    )
    success_count += 1
    processed += 1
    continue  # ✅ 必须 continue，防止进入 else 块
else:
    # 归档全链路
    library_root = db.get_active_library_path(refined_type)
    # ... 移动文件 ...
    SmartLink.create_link(file_path, target_path)
```

### 关键改动
1. 删除内层 `if task.get("status") == "archived":` 判断
2. 无论 status 是什么，都执行 `db.update_any_task_metadata()`
3. 无论 status 是什么，都执行 `continue`

---

## 部署检查清单

- [ ] 修改 `perform_scrape_all_task_sync()` 的锁处理逻辑
- [ ] 修改 `perform_scrape_all_task_sync()` 中的 `success_count` 计数
- [ ] 修改 `update_task_status()` 的归档触发位置
- [ ] 修改 `get_tasks_needing_scrape()` 的事务处理
- [ ] 修改 `perform_scrape_all_task_sync()` 中的就地补录逻辑
- [ ] 运行 `pytest` 确保单元测试通过
- [ ] 在开发环境测试并发场景
- [ ] 在生产环境验证功能正常
