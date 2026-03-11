# 媒体库组件 - `components/media/`

---

## 一、`StatsOverview.tsx`

Dashboard 统计卡片 + 指令舱。

- 调用 `api.getStats()` → `GET /api/v1/stats`
- **不做轮询**，仅在以下时机主动刷新：
  - 首次加载
  - 点击 Scan 按钮后（扫描期间每 1.5s 刷新，最多 30s，用于更新 pending 计数）
  - 点击 Scrape / Find Subtitles 按钮后（1s 后刷新一次）
- 四张卡片：电影数 / 剧集总集数 / 待处理 / 已完成
- **COMMAND CENTER** 指令舱包含三个功能按钮：

| 按钮 | API | i18n key（标题/进行中）|
|---|---|---|
| Scan | `api.triggerScan()` | `dashboard_btn_scan` / `stat_scanning_active` |
| Scrape | `api.triggerScrapeAll()` | `dashboard_btn_scrape` / `stat_scraping_active` |
| Find Subtitles | `api.triggerFindSubtitles()` | `dashboard_btn_find_subtitles` / `stat_finding_subtitles_active` |

---

## 二、`MiniLog.tsx`

全息日志流，Dashboard 下半区。

- 调用 `api.getSystemLogs()` → `GET /api/v1/logs`，15s 轮询
- 支持按标签过滤（`SCAN` / `TMDB` / `ERROR` 等）
- 日志着色：`ERROR` 红色、`WARNING` 黄色、`INFO` 青色

---

## 三、`MediaWall.tsx`

媒体库主视图容器，组合 `MediaToolbar` + `MediaTable` + `MediaPagination`。

- 持有分页/筛选/搜索/选中状态
- 调用 `api.getTasks()` 获取任务列表（前端分页，一次拉取全量后本地分页）
- 搜索防抖 500ms
- 包含批量删除二次确认弹窗和清空数据库（CONFIRM 输入确认）弹窗

**Toast 提示 i18n key：**

| 操作 | 成功 key | 失败 key |
|---|---|---|
| 扫描触发 | `ai_scan_triggered` | — |
| 删除单条 | `delete_record_success` | `task_delete` + `op_failed` |
| 批量删除 | `delete_record_success` + 条数 | `task_delete` + `op_failed` |
| 重置数据库 | `purge_success` + 条数 | `op_reset_failed` |
| 批量删除按钮加载态 | `op_deleting` | — |

---

## 四、`MediaTable.tsx`

任务列表，每行一个媒体任务。

### 操作按钮

| 操作 | 条件 | API |
|---|---|---|
| 重试 | `status === 'failed'` | `api.retryTask(id)` |
| 删除 | 所有行 | `api.deleteTask(id)` |
| TMDB 链接 | 有 `tmdb_id` | 外链 |
| IMDb 链接 | 有 `imdb_id` | 外链 |

### 国际化 key

| 元素 | i18n key |
|---|---|
| 无数据提示 | `no_data` |
| 无数据副文本 | `task_no_data_hint` |
| 时间戳兜底 | `task_just_now` |
| 入库路径标签 | `path_dst` |
| 原始路径标签 | `path_src` |

### 流水线进度条

每行底部显示实际流水线进度，由任务真实状态驱动：

| 状态 | 字幕状态 | 进度 | 颜色 |
|---|---|---|---|
| `pending` | 任意 | 30% | 青色 |
| `archived`/`scraped` | 无/missing/failed | 60% | 青色 |
| `archived`/`scraped` | `scraped`/`found`/`success` | 100% | 青色→绿色 |
| `failed`/`ignored` | 任意 | 不显示 | — |

进度条带 `transition-all duration-700` 平滑动画。

### 状态徽章

| 状态 | 颜色 |
|---|---|
| `archived` | 青色 |
| `failed` | 红色 |
| `ignored` | 灰色 |
| `pending` | 青色淡 |

---

## 五、`MediaToolbar.tsx`

媒体库工具栏，包含：
- 搜索框（placeholder: `toolbar_search_placeholder`）
- 刷新按钮（`toolbar_refresh`）
- 批量删除按钮（`toolbar_delete`，有选中项时激活）
- 重置数据库按钮（`toolbar_reset`）
- 状态/类型过滤下拉（`filter_status` / `filter_type`）
- 扫描 / 刮削 / 字幕触发按钮（带 loading 状态）

**按钮 i18n key：**

| 按钮 | 默认 | 进行中 |
|---|---|---|
| 扫描 | `toolbar_scan` | `dashboard_btn_scanning` |
| 刮削 | `toolbar_scrape` | `dashboard_btn_scraping` |
| 字幕 | `toolbar_subtitles` | `dashboard_btn_finding` |

---

## 六、`MediaPagination.tsx`

前端分页控件，每页 20 条，显示当前页/总页数。

---

## 七、`SystemMonitor.tsx`

系统监控页面，展示实时日志流（支持多标签过滤）。

**硬编码标题已全部 i18n 化：**

| 元素 | i18n key |
|---|---|
| QUANTUM STREAM 标题 | `monitor_quantum_stream` |
| MEMORY READOUT 副标题 | `monitor_memory_readout` |
| FILTERS 标签 | `monitor_filters` |
| INFO 统计标签 | `monitor_level_info` |
| WARNING 统计标签 | `monitor_level_warning` |
| ERROR 统计标签 | `monitor_level_error` |
| 自动滚动 | `monitor_auto_scroll` |
| 清空日志 | `monitor_clear_logs` |
| 等待日志 | `monitor_waiting_logs` |

---

## 八、国际化完整性

所有 media 组件已完全国际化，无硬编码字符串。详见 `lib/i18n.ts` 完整 key 列表。

---

*最后更新：2026-03-11*
