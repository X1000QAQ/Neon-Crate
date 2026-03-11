# 类型定义 - `types/index.ts`

> 路径：`frontend/types/index.ts`

---

## 一、类型列表

### `Task`

| 字段 | 类型 | 说明 |
|---|---|---|
| `status` | `'pending'\|'scraped'\|'failed'\|'archived'\|'ignored'` | 任务状态（已修正，删除旧 `'success'`）|
| `sub_status` | `'pending'\|'scraped'\|'failed'\|'missing'?` | 字幕状态（已修正）|
| `auto_process_enabled` | `boolean` | 前端 UI 专用：自动流水线总开关，后端忽略此字段 |

其余字段详见源码 `frontend/types/index.ts`。

---

## 二、与后端类型对比（已全部修正）

| 问题 | 修正内容 |
|---|---|
| `Task.status` 含 `'success'` | 已改为 `'scraped'` |
| `Task.sub_status` 含 `'success'` | 已改为 `'scraped'`，删除重复值 |
| `settings.auto_process_enabled` 缺失 | 已恢复并加注释：前端 UI 专用 |
| `purgeAllTasks()` 参数 `{confirm}` | 已改为 `{status: 'failed'}` |
| `Task.type` 与 `Task.media_type` 语义重复 | 已删除冗余的 `type?: 'movie' \| 'tv'`，统一使用 `media_type` |

---

## 三、`SettingsConfig.settings` 字段

| 字段 | 说明 |
|---|---|
| `cron_enabled` | 定时巡逻开关 |
| `cron_interval_min` | 巡逻间隔（分钟）|
| `auto_process_enabled` | 前端 UI 专用，控制子开关显隐 |
| `auto_scrape` | 扫描后自动刮削 |
| `auto_subtitles` | 刮削后自动搜字幕 |
| `min_size_mb` | 文件大小过滤阈值 |

---

*最后更新：2026-03-11*
