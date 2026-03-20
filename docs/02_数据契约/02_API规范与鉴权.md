# API 规范与鉴权架构

**文档编号**：CONTRACT-002  
**版本**：v1.0.0-Stable  
**最后更新**：2026-03-20  

---

## 一、鉴权架构

| 特性 | 值 |
|------|----|
| 算法 | HS256 |
| 有效期 | 7 天 |
| 存储 | `localStorage.token` |
| 传输 | `Authorization: Bearer <token>` |

```
路由分层：
/api/v1/auth/*   无 JWT（登录/初始化）
/api/v1/*        有 JWT（全局 Depends 注入）
/public/*        无 JWT（路径安全机制保护）
/health          无 JWT（健康检查）
```

---

## 二、鉴权端点（/api/v1/auth）

| 方法 | 路径 | 请求体 | 响应 |
|------|------|--------|------|
| GET | `/auth/status` | — | `{initialized: bool}` |
| POST | `/auth/init` | `{username, password}` | `TokenResponse` |
| POST | `/auth/login` | `{username, password}` | `TokenResponse` |
| GET | `/auth/verify` | — | `{valid: true}` |

---

## 三、任务端点（/api/v1/tasks）

### 触发类
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tasks/scan` | 物理扫描 |
| GET | `/tasks/scan/status` | 扫描状态 |
| POST | `/tasks/scrape_all` | 全量刮削 |
| GET | `/tasks/scrape_all/status` | 刮削状态 |
| POST | `/tasks/find_subtitles` | 字幕查找 |
| GET | `/tasks/find_subtitles/status` | 字幕状态 |
| POST | `/tasks/manual_rebuild` | 手动补录或全量重建（见下文） |
| GET | `/tasks/search_tmdb` | TMDB 关键词搜索（补录弹窗候选，最多 10 条） |

### 媒体库操作
| 方法 | 路径 | 说明 | is_archive 传递 |
|------|------|------|----------------|
| GET | `/tasks/` | 列表（分页+搜索+过滤）| 响应包含 is_archive |
| GET | `/tasks/{id}` | 单条详情 | 响应包含 is_archive |
| DELETE | `/tasks/{id}` | 删除（双表清理）| 请求体需包含 is_archive |
| POST | `/tasks/delete_batch` | `{ids:[…], is_archive: bool}` 批量删除 | 🚨 必须传递 |
| POST | `/tasks/purge` | `{confirm:'CONFIRM'}` 清空 | 无 |
| POST | `/tasks/{id}/retry` | 重试失败任务 | 请求体需包含 is_archive |
| POST | `/tasks/{id}/ignore` | 标记 ignored | 请求体需包含 is_archive |
| POST | `/tasks/{id}/archive` | 手动归档 | 请求体需包含 is_archive |
| POST | `/tasks/manual_rebuild` | 手动补录 / 全量重建 | 🚨 必须传递 `is_archive` |

### 设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks/settings` | 读取完整配置 |
| POST | `/tasks/settings` | 保存（1+1路径约束）|
| POST | `/tasks/settings/reset` | `{target:'ai'\|'regex'}` |

---

## 四、手动补录与全量重建（`/api/v1/tasks/manual_rebuild`）

### 路由职责划分

| 标志 | 引擎 | 语义 |
|------|------|------|
| `nuclear_reset: false`（默认） | `AssetPatchEngine` | **补录（Patch）**：在门控允许时重写 NFO/海报/字幕，物理位移受 `path_changed` 等约束 |
| `nuclear_reset: true` | `NuclearEngine` | **全量重建**：按 `scope`（`series` / `season` / `episode`）走 TV 批量或单集/电影主轴，可搬迁视频与级联清理空目录 |

### POST /tasks/manual_rebuild

**请求体（与 `ManualRebuildRequest` 对齐）**：
```json
{
  "task_id": 123,
  "is_archive": true,
  "tmdb_id": 550,
  "keyword_hint": null,
  "media_type": "movie",
  "refix_nfo": true,
  "refix_poster": true,
  "refix_subtitle": true,
  "nuclear_reset": false,
  "season": 1,
  "episode": 1,
  "scope": "episode"
}
```

- **`is_archive`**：🚨 必传语义——`false` 查热表 `tasks`，`true` 查冷表 `media_archive`（列表里的 `id` 对冷表即为 `original_task_id`）。
- **`scope`**：TV 全量重建时使用；`episode` 时请求体中的 `season`/`episode` 可覆盖库内值。
- **`tmdb_id`**：可选；缺省时尝试用任务记录中的 TMDB；若有则拉 TMDB 详情补齐 title/year/imdb。

**响应体（字段随引擎路径略有差异，典型结构）**：
```json
{
  "success": true,
  "rebuilt": {
    "nfo": true,
    "poster": true,
    "subtitle": "skipped",
    "nuclear": false
  },
  "message": "msg_rebuild_success_patch_movie"
}
```

`message` 多为 i18n 键或后端消息键，由前端 `t()` 映射展示。

**服务端主路径**：
1. 按 `is_archive` 加载任务行，校验 `target_path` / `metadata_dir`。
2. 解析 `library_root`；**TV** 下与白名单 `paths` 纠偏，避免误用 download 目录。
3. 配置 TMDB Key 与 `MetadataManager`，组装 `ctx`（含 `new_tmdb_id`、`task_season`、`task_episode` 等）。
4. 分支调用 `NuclearEngine` 或 `AssetPatchEngine.execute()`（同步执行，可能较慢；前端 `api.rebuildTask` 使用延长超时）。

### GET /tasks/search_tmdb

- **Query**：`keyword`（必填）、`media_type`（默认 `movie`，支持 `tv`）。
- **响应**：`{ tmdb_id, title, year, overview, poster_path, imdb_id }[]`，最多 10 条。
- **错误**：未配置 TMDB Key → 500；上游失败 → 502。

---

## 五、系统端点（/api/v1/system）

### GET /system/stats

```json
{ "movies": 120, "tv_shows": 450, "pending": 3, "completed": 162 }
```

缓存模式：扫描/刮削完成后更新，不实时扫盘。

### GET /system/logs

Query: `?tags=SCAN,TMDB,ERROR`

支持标签：`SCAN TMDB SUBTITLE ERROR API ORGANIZER LLM AI META DB SECURITY DEBUG`

### GET /public/image

Query: `?path=<URL编码路径>`

安全防护：`Path.resolve()` + 目录黑名单 + 后缀白名单（`.jpg/.png/.webp/.gif`）

---

## 六、AI 对话端点（/api/v1/agent）

### POST /agent/chat

请求：`{"message": "帮我下载星际穿越"}`

响应：
```json
{
  "response": "正在为你寻找资源...",
  "action": "DOWNLOAD",
  "engine_tag": "cloud"
}
```

意图码：
| action | 前端行为 |
|--------|----------|
| `ACTION_SCAN` | 调用 `api.triggerScan()` |
| `ACTION_SCRAPE` | 调用 `api.triggerScrapeAll()` |
| `ACTION_SUBTITLE` | 调用 `api.triggerFindSubtitles()` |
| `DOWNLOAD` | 后端 agent 内部已完成，前端无需处理 |
| `null` | 纯对话或候选展示阶段 |

---

## 七、前端调用规范

```typescript
// ✅ 正确：通过 lib/api.ts 调用
const stats = await api.getStats();

// ❌ 错误：裸 fetch
const res = await fetch('/api/v1/system/stats');
```

### 图片加载协议

```typescript
// 本地图片 → 安全代理
`/api/v1/public/image?path=${encodeURIComponent(localPath)}`

// HTTP URL → 浏览器直连
if (posterPath?.startsWith('http')) return posterPath;
```

### 401 自动清退

`secureFetch` 拦截 401 → `localStorage.removeItem('token')` → 跳转 `/auth/login`，无需组件层感知。

---

## 八、后端开发规范

- 所有新增业务 API 必须通过 `api_router` 挂载，不得绕过全局 JWT 依赖
- 所有过滤规则必须来自数据库，严禁硬编码
- 图片访问必须通过 `/api/v1/public/image` 代理
- 设置保存前必须执行 1+1 路径约束校验

*Neon Crate 系统架构师 | v1.0.0-Stable | 2026-03-20*
