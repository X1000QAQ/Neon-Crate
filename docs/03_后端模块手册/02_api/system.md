# 系统端点手册 - `app/api/v1/endpoints/system.py`

> 路径：`backend/app/api/v1/endpoints/system.py`
> 路由前缀：`/api/v1`（`router`）和 `/api/v1/public`（`public_router`）

---

## 一、接口列表

### `GET /api/v1/stats`（需 JWT）

返回媒体库统计数据。

**响应：`StatsResponse`**
```json
{
  "movies": 120,
  "tv_shows": 450,
  "pending": 3,
  "completed": 162
}
```

**实现（缓存模式）：**
- `movies` / `tv_shows` 从数据库缓存读取（`library_movies_count` / `library_tv_count`），**不实时扫描硬盘**
- `pending` / `completed` 实时读取 `tasks` 表（纯 SQL，无 I/O 压力）

**缓存更新时机（触发物理扫盘写入缓存）：**
- 手动点击 Scan 按钮 → `perform_scan_task()` 完成后调用 `_update_library_counts()`
- 手动点击 Scrape 按钮 → `perform_scrape_all_task_sync()` 完成后调用 `_update_library_counts()`
- AI 意图触发扫描/刮削 → 同上
- 定时巡逻完成相应步骤 → 同上

**`_update_library_counts()` 统计规则：**
- 电影：统计电影媒体库第一层子文件夹数（每个文件夹 = 一部电影）
- 剧集：递归统计剧集媒体库所有视频文件数（每个文件 = 一集）

⚠️ 旧版直接在接口里 `os.walk` 扫描硬盘，前端每 5 秒调用一次，对 NAS 造成持续 I/O 压力，已改为缓存模式。

---

### `GET /api/v1/logs`（需 JWT）

读取系统日志，支持按标签过滤。

**Query 参数：**
- `tags`：逗号分隔的标签，如 `SCAN,TMDB,ERROR`

**支持的标签：**
`SCAN` / `TMDB` / `SUBTITLE` / `ERROR` / `API` / `ORGANIZER` / `ORG` / `CLEAN` / `LLM` / `AI` / `AI-EXEC` / `META` / `DB` / `SECURITY` / `DEBUG`

**响应：**
```json
{
  "logs": [
    {"timestamp": "2026-03-11T10:00:00.000", "level": "INFO", "message": "...", "tag": "SCAN"}
  ],
  "source": "/path/to/app.log",
  "total": 156
}
```

---

### `GET /api/v1/public/image`（需 JWT）

安全图片代理，通过 `path` 参数代理本地图片文件。

**安全机制：**
- `Path.resolve()` 防御 `../` 路径穿越
- 动态黑名单拦截系统敏感目录
- 仅允许 `.jpg` / `.jpeg` / `.png` / `.webp` / `.gif`
- 文件不存在返回 `HTTP 404`

---

## 二、日志解析说明

`_parse_log_line()` 兼容两种格式：

**标准格式：**
```
2026-03-11 10:00:00,000 - app.module - INFO - [SCAN] message
```

**非标准格式（print 输出）：**
直接作为 `INFO` 级别保留，尝试从文本中提取 `[TAG]` 标签。

---

## 三、注意事项

- `stats` 端点直接统计物理文件夹，不依赖数据库计数，数据最准确
- 日志文件路径硬编码为 `BASE_DIR/data/logs/app.log`，`BASE_DIR` 从 `system.py` 文件位置向上 5 层推算
- `public_router` 挂载在 `/api/v1/public` 下，同样受 JWT 保护

---

*最后更新：2026-03-11*
