# API 规范与鉴权架构

**文档编号**：CONTRACT-002  
**版本**：v1.0.0-Stable  
**最后更新**：2026-03-14  

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
| POST | `/tasks/manual_rebuild` | 核级重构 | 🚨 必须传递 is_archive |

### 设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/tasks/settings` | 读取完整配置 |
| POST | `/tasks/settings` | 保存（1+1路径约束）|
| POST | `/tasks/settings/reset` | `{target:'ai'\|'regex'}` |

---

## 五、核级重构端点（/api/v1/tasks/manual_rebuild）— v1.0.0

### POST /tasks/manual_rebuild

**请求体**：
```json
{
  "task_id": 123,
  "is_archive": true,              // 🚨 必须传递：0=热表，1=冷表
  "tmdb_id": 550,
  "keyword_hint": "The Matrix",
  "media_type": "movie",
  "refix_nfo": true,
  "refix_poster": true,
  "refix_subtitle": true,
  "nuclear_reset": true,           // 核级清理标志
  "season": 1,                     // TV 专用
  "episode": 1                     // TV 专用
}
```

**响应体**：
```json
{
  "success": true,
  "task_id": 123,
  "title": "The Matrix",
  "tmdb_id": 550,
  "rebuilt": {
    "nfo": true,                   // NFO 是否成功写入
    "poster": true,                // 海报是否成功下载
    "subtitle": "success",         // 字幕状态：success/pending/failed
    "nuclear": true                // 核级清理是否执行
  },
  "message": "核级重构完成"
}
```

**业务链路**：
1. 根据 `is_archive` 选择查询表（热表 tasks 或冷表 media_archive）
2. 校验 `target_path` 有效性
3. 初始化 TMDB 适配器
4. 金标准防重预检（检查本地 NFO 中的 IMDb ID）
5. 核级清理（删除旧 NFO、海报、Fanart）
6. 视频文件重命名
7. 文件夹土木工程
8. 调用 `update_any_task_metadata()`（更新元数据）
9. 调用 `update_task_status()`（触发归档流程）
10. NFO 生成与写入
11. 海报下载与存储
12. 字幕检测（本地白嫖）
13. 返回重建结果

**关键设计**：
- **is_archive 致命重要**：决定操作哪张表，若未传递则后端无法确定
- **物理感知护盾**：金标准 IMDb 校验通过后，仍需 `NFO 存在 + poster.* 物理存在` 才允许短路；若 **有 NFO 但无海报**，系统将强制解除护盾触发补领
- **TV 季/集号作用域护盾**：`season/episode` 在 `manual_rebuild` 生命周期内提前初始化（请求优先、DB 兜底），保证非核级精准补录同样能写回 DB，避免 TV 单点补录触发 `UnboundLocalError`
- **核级清理**：删除旧元数据文件，确保新数据写入无冲突
- **字幕白嫖**：归档完成后立即检测本地字幕，零 API 消耗

---

## 六、系统端点（/api/v1/system）

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

## 七、AI 对话端点（/api/v1/agent）

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

## 八、前端调用规范

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

## 七、后端开发规范

- 所有新增业务 API 必须通过 `api_router` 挂载，不得绕过全局 JWT 依赖
- 所有过滤规则必须来自数据库，严禁硬编码
- 图片访问必须通过 `/api/v1/public/image` 代理
- 设置保存前必须执行 1+1 路径约束校验

*Neon Crate 系统架构师 | v1.0.0-Stable | 2026-03-14*
