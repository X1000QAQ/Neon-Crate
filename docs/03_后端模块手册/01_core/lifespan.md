# lifespan.py — 生命周期管理 + 自动巡逻流水线

**文件路径**: `backend/app/core/lifespan.py`  
**核心函数**: `lifespan(app)` (asynccontextmanager)

---

## 职责

管理 FastAPI 应用的完整生命周期：
1. **启动阶段**：日志 → 数据库 → 孤儿任务清理 → 启动巡逻协程
2. **运行阶段**：`cron_scanner_loop()` 异步无限循环
3. **关闭阶段**：取消巡逻协程，优雅退出

---

## 启动序列

```
lifespan() 启动
  │
  ├─ _setup_logging()          → RotatingFileHandler (10MB×5) + StreamHandler
  │    日志路径: data/logs/app.log
  │
  ├─ _check_environment()      → 检查 /storage 挂载点是否存在
  │
  ├─ get_db_manager()          → 初始化 SQLite (WAL 模式 + 原子写入)
  │
  ├─ 孤儿任务清理               → db.reset_orphan_pending_tasks()
  │    重置上次崩溃遗留的 is_running 状态
  │    重置内存状态字典 scrape_all_status / find_subtitles_status
  │
  └─ asyncio.create_task(cron_scanner_loop())
       启动自动巡逻协程
```

---

## cron_scanner_loop() — 自动巡逻流水线

### 配置读取（每轮动态读取，热更新无需重启）

| 配置键 | 类型 | 说明 |
|--------|------|------|
| `cron_enabled` | bool | 总开关，关闭时跳过本轮 |
| `cron_interval_min` | int | 巡逻间隔（分钟），默认 60 |
| `auto_scrape` | bool | 扫描完成后是否自动刮削 |
| `auto_subtitles` | bool | 刮削完成后是否自动搜索字幕 |

### 流水线执行逻辑

```
每轮循环：
  1. 读取配置（热更新）
  2. cron_enabled=OFF → 跳过，等待下一轮
  3. cron_enabled=ON：
     ├─ 步骤1: perform_scan_task()           物理扫描 + 智能入库
     ├─ 步骤2: perform_scrape_all_task_sync() [auto_scrape=ON 时]
     │           全量刮削（线程池执行）
     └─ 步骤3: perform_find_subtitles_task_sync() [auto_subtitles=ON 时]
                字幕补全（线程池执行）
  4. sleep(interval_seconds)
```

### 防重叠保护

巡逻循环在触发刮削/字幕前检查对应状态字典：

```python
if scrape_all_status["is_running"]:
    logging.warning("[CRON] 刮削任务正在执行中，本轮跳过")
else:
    await asyncio.get_event_loop().run_in_executor(None, perform_scrape_all_task_sync)
```

### 异常恢复

```python
except Exception as e:
    db.set_config("cron_last_error", str(e))
    db.set_config("cron_last_error_time", datetime.now().isoformat())
    await asyncio.sleep(60)   # 60 秒后重试，不中断循环
```

错误信息持久化到数据库，前端可通过 `/api/v1/system/stats` 或日志接口查询。

---

## 关闭序列

```python
cron_task.cancel()
try:
    await cron_task
except asyncio.CancelledError:
    pass   # 正常退出
```

---

## 日志配置

| 配置项 | 值 |
|--------|----|
| 日志文件 | `data/logs/app.log` |
| 轮转大小 | 10 MB |
| 保留份数 | 5 份 |
| 格式 | `%(asctime)s - %(name)s - %(levelname)s - %(message)s` |
| 输出 | 文件 + 控制台同时输出 |
