# API 客户端 - `lib/api.ts`

> 路径：`frontend/lib/api.ts`

---

## 一、核心工具函数

### `secureFetch(url, options)`
- 15s 超时（`AbortController`）
- 网络错误 → `notifyLinkDown()` 触发断链弹窗
- 401 → 清除 token，跳转 `/auth/login`
- 5xx → `notifyLinkDown()`

### `getHeaders(includeAuth)` 
自动附加 `Authorization: Bearer {token}`。

### `safeJson<T>(res)`
验证 `Content-Type: application/json`，否则抛 `ApiError`。

---

## 二、API 方法（已修正）

### 鉴权（不经过 secureFetch）
| 方法 | 接口 |
|---|---|
| `authStatus()` | `GET /auth/status` |
| `initAuth()` | `POST /auth/init` |
| `login()` | `POST /auth/login` |

### 任务
| 方法 | 接口 | 说明 |
|---|---|---|
| `getTasks(params)` | `GET /tasks` | 分页查询 |
| `deleteTask(id)` | `DELETE /tasks/{id}` | 单条删除 |
| `deleteBatchTasks(ids)` | `POST /tasks/delete_batch` | 批量删除 |
| `purgeAllTasks()` | `POST /tasks/purge` | 清空（请求体：`{confirm:'CONFIRM'}`，与后端 `PurgeRequest.confirm` 对齐）|
| `retryTask(id)` | `POST /tasks/{id}/retry` | 重试 |

### 触发任务
| 方法 | 接口 |
|---|---|
| `triggerScan()` | `POST /tasks/scan` |
| `triggerScrapeAll()` | `POST /tasks/scrape_all` |
| `triggerFindSubtitles()` | `POST /tasks/find_subtitles` |

### 设置
| 方法 | 接口 |
|---|---|
| `getSettings()` | `GET /tasks/settings` |
| `updateSettings(config)` | `POST /tasks/settings` |
| `resetSettings(target)` | `POST /tasks/settings/reset` |

### 其他
| 方法 | 接口 |
|---|---|
| `getStats()` | `GET /system/stats` |
| `getSystemLogs(tags?)` | `GET /system/logs` |
| `chat(message)` | `POST /agent/chat` |

---

*最后更新：2026-03-11*
