# 定时巡逻与应用生命周期 - `app/main.py`

> 路径：`backend/app/main.py`

---

## 一、概述

FastAPI 应用入口，负责：生命周期管理、日志系统初始化、路由注册、静态资源挂载、全自动巡逻流水线。

---

## 二、自动巡逻流水线 `cron_scanner_loop()`

应用启动时通过 `asyncio.create_task()` 在后台持续运行。

### 完整流水线

```
每轮开始
  ├─► 读取 cron_enabled
  │     = False → 跳过本轮，等待下一个间隔
  │     = True  ↓
  ├─► 步骤1：await perform_scan_task()        物理扫描 + 智能入库
  ├─► 读取 auto_scrape
  │     = False → 跳过步骤2和3
  │     = True  ↓
  ├─► 步骤2：run_in_executor(perform_scrape_all_task_sync)  全量刮削
  │     ├─► 检查 scrape_all_status["is_running"] 防重叠
  │     └─► 刮削完成后 ↓
  ├─► 读取 auto_subtitles
  │     = False → 跳过步骤3
  │     = True  ↓
  └─► 步骤3：run_in_executor(perform_find_subtitles_task_sync)  字幕搜索
        └─► 检查 find_subtitles_status["is_running"] 防重叠

等待 cron_interval_min 分钟后执行下一轮
```

### 配置读取

| 配置键 | 类型 | 说明 |
|---|---|---|
| `cron_enabled` | bool | 巡逻总开关 |
| `cron_interval_min` | int | 巡逻间隔（分钟），默认 60，≤0 时回退到 60 |
| `auto_scrape` | bool | 扫描后自动刮削 |
| `auto_subtitles` | bool | 刮削后自动搜索字幕（依赖 auto_scrape=True）|

### 防重叠机制

步骤2和步骤3在执行前检查对应的 `is_running` 状态，若上一轮任务未完成则跳过本轮，避免任务堆积。

### 异常处理

- `asyncio.CancelledError`：应用关闭时优雅退出
- 其他异常：打印错误日志，60 秒后重试

---

## 三、路由注册

| 前缀 | 路由 | 鉴权 |
|---|---|---|
| `/api/v1/auth` | `auth_router` | 无 JWT |
| `/api/v1/public` | `public_system_router` | 有 JWT |
| `/api/v1` | `api_router`（所有业务路由）| 有 JWT |

---

## 四、静态资源挂载

| 路径 | 目录 | 说明 |
|---|---|---|
| `/api/v1/assets` | Docker `/storage` 或本地 `data/posters` | 海报/图片资源 |
| `/` | `static/` | AIO 模式前端静态文件（可选）|

---

## 五、SPA 404 回退

- `/api/*` 请求 → 返回 JSON 404
- 其他路径 → 返回 `static/index.html`（前端路由接管）

---

*最后更新：2026-03-11*
