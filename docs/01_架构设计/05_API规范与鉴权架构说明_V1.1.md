# Neon Crate API 规范与鉴权架构说明

**文档编号**：ARCH-API-005  
**版本**：V1.1  
**编制日期**：2026-03-11  
**状态**：已生效  
**维护者**：Neon Crate 系统架构师  
**适用范围**：HTTP API 规范、JWT 鉴权流程、前后端交互契约  
**目标受众**：全栈工程师、架构评审

---

## 文档概述

本文档定义 Neon Crate 系统的 API 规范、鉴权架构、前后端交互契约，确保所有接口遵循统一的设计原则和安全标准。

## 文档概述

本文档定义 Neon Crate 系统的 API 规范、鉴权架构、前后端交互契约。核心原则：

- **默认拦截，显式豁免**：所有 `/api/v1/*` 业务路由默认要求 JWT，仅少量端点（登录、初始化、公共资源）豁免
- **数据库驱动**：所有过滤规则、AI 规则来自数据库，严禁硬编码
- **前后端契约清晰**：统一的请求封装、Token 注入、错误处理

---

## 一、鉴权架构

### 1.1 JWT 无状态鉴权

**核心实现**：

| 组件 | 位置 | 职责 |
|---|---|---|
| Token 生成 | `app/api/auth.py` | `create_access_token(username)` 生成 JWT |
| Token 校验 | `app/api/auth.py` | `verify_token(token)` 校验有效性 |
| 全局依赖 | `app/api/auth.py` | `get_current_user()` 注入到所有受保护路由 |
| 路由挂载 | `app/main.py` | `dependencies=[Depends(get_current_user)]` |

**Token 特性**：

- 默认有效期：7 天
- 存储位置：前端 `localStorage.token`
- 传输方式：`Authorization: Bearer <token>` Header
- 算法：HS256（HMAC SHA-256）

### 1.2 路由分层

```
/api/v1/auth/*
  ├─ GET /status          (无需 JWT - 检查初始化状态)
  ├─ POST /init           (无需 JWT - 首次初始化)
  ├─ POST /login          (无需 JWT - 登录获取 Token)
  └─ GET /verify          (需 JWT - 验证 Token 有效性)

/api/v1/*（业务路由）
  ├─ /tasks/*             (需 JWT - 任务管理)
  ├─ /system/stats        (需 JWT - 系统统计)
  ├─ /system/logs         (需 JWT - 系统日志)
  └─ /agent/chat          (需 JWT - AI 对话)

/api/v1/public/*（公共路由）
  └─ /image               (无需 JWT - 图片代理，依赖路径安全机制)
```

**安全语义**：

- `/api/v1/auth/*`：显式豁免 JWT，用于初始化与登录流程
- `/api/v1/*`：全局强制 JWT 保护（通过 `api_router` 的 `dependencies` 注入）
- `/api/v1/public/*`：豁免 JWT，但通过路径安全机制（黑名单、后缀白名单）防御

---

## 二、鉴权端点（`/api/v1/auth`）

### 2.1 `GET /auth/status`

检查系统是否已初始化管理员账号。

**请求**：无参数

**响应**：`AuthStatusResponse`

```json
{
  "initialized": true,
  "message": "系统已初始化"
}
```

**用途**：前端启动时检查是否需要跳转到初始化页面

---

### 2.2 `POST /auth/init`

首次初始化管理员账号（**仅允许执行一次**）。

**请求体**：`InitRequest`

```json
{
  "username": "admin",
  "password": "123456"
}
```

**限制**：
- 用户名长度 ≥ 3 字符
- 密码长度 ≥ 6 字符
- 若已初始化，返回 `HTTP 400`

**响应**：`TokenResponse`

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "username": "admin"
}
```

---

### 2.3 `POST /auth/login`

登录验证，返回 JWT Token。

**请求体**：`LoginRequest`

```json
{
  "username": "admin",
  "password": "123456"
}
```

**响应**：`TokenResponse`

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "username": "admin"
}
```

**错误**：
- `HTTP 400`：系统未初始化
- `HTTP 401`：用户名或密码错误

---

### 2.4 `GET /auth/verify`

验证 Token 有效性。

**请求头**：`Authorization: Bearer <token>`

**响应**：`{"valid": true}`

**错误**：`HTTP 401` - Token 无效或过期

---

## 三、任务端点（`/api/v1/tasks`）

### 3.1 任务查询

#### `GET /tasks`

查询任务列表（分页 + 搜索 + 过滤）。

**Query 参数**：

| 参数 | 类型 | 说明 |
|---|---|---|
| `page` | int | 页码（默认 1）|
| `page_size` | int | 每页数量（默认 20）|
| `status` | string | 状态过滤：`all` / `pending` / `scraped` / `failed` / `archived` / `ignored` |
| `media_type` | string | 类型过滤：`all` / `movie` / `tv` |
| `search` | string | 关键词搜索（模糊匹配文件名/标题）|

**响应**：`TasksResponse`

```json
{
  "tasks": [
    {
      "id": 1,
      "file_path": "/mnt/storage/movies/Dune.Part.Two.2024.mkv",
      "file_name": "Dune.Part.Two.2024.mkv",
      "media_type": "movie",
      "status": "archived",
      "title": "Dune Part Two",
      "year": 2024,
      "season": null,
      "episode": null,
      "tmdb_id": 693134,
      "poster_path": "/abc123.jpg",
      "local_poster_path": "/storage/posters/movie_693134.jpg",
      "created_at": "2026-03-11T10:00:00"
    }
  ],
  "total": 156,
  "page": 1,
  "page_size": 20
}
```

#### `GET /tasks/{task_id}`

获取单条任务详情。

**响应**：`Task` 对象

---

### 3.2 任务操作

#### `DELETE /tasks/{task_id}`

删除单条任务（同时清理 `media_archive` 残留）。

**响应**：`{"message": "任务已删除"}`

#### `POST /tasks/delete_batch`

批量删除任务。

**请求体**：`DeleteBatchRequest`

```json
{
  "ids": [1, 2, 3]
}
```

**响应**：`{"message": "已删除 3 条任务"}`

#### `POST /tasks/purge`

清空所有任务（**不可撤销**）。

**请求体**：`PurgeRequest`

```json
{
  "confirm": "CONFIRM"
}
```

**响应**：`{"deleted": 156}`

#### `POST /tasks/{task_id}/retry`

重试失败任务（重新刮削）。

**响应**：`{"message": "任务已重新加入队列"}`

#### `POST /tasks/{task_id}/ignore`

标记任务为 ignored（跳过处理）。

**响应**：`{"message": "任务已标记为忽略"}`

---

### 3.3 扫描任务

#### `POST /tasks/scan`

触发物理扫描（后台异步执行）。

**请求体**：无

**响应**：`ScanResponse`

```json
{
  "message": "扫描任务已启动",
  "task_id": "scan_20260311_100000"
}
```

**防重复**：扫描运行中再次触发返回 `"任务已在运行中"`

#### `GET /tasks/scan/status`

查询扫描任务运行状态。

**响应**：

```json
{
  "is_running": false,
  "last_scan_time": "2026-03-11T10:00:00",
  "files_found": 156,
  "files_processed": 156
}
```

---

### 3.4 刮削任务

#### `POST /tasks/scrape_all`

触发全量刮削（后台线程执行）。

**请求体**：无

**响应**：`ScanResponse`

```json
{
  "message": "刮削任务已启动",
  "task_id": "scrape_20260311_100000"
}
```

#### `GET /tasks/scrape_all/status`

查询刮削任务状态。

**响应**：

```json
{
  "is_running": false,
  "last_run_time": "2026-03-11T10:00:00",
  "tasks_processed": 156,
  "tasks_success": 150,
  "tasks_failed": 6
}
```

---

### 3.5 字幕任务

#### `POST /tasks/find_subtitles`

触发全量字幕查找。

**请求体**：无

**响应**：`ScanResponse`

#### `GET /tasks/find_subtitles/status`

查询字幕任务状态。

**响应**：

```json
{
  "is_running": false,
  "last_run_time": "2026-03-11T10:00:00",
  "tasks_processed": 156,
  "subtitles_found": 145
}
```

---

### 3.6 设置管理

#### `GET /tasks/settings`

读取完整系统配置。

**响应**：`SettingsConfig`

```json
{
  "settings": {
    "ui_lang": "zh",
    "min_size_mb": 50,
    "filename_clean_regex": "...",
    "cron_enabled": false,
    "cron_interval_min": 60,
    "auto_process_enabled": false,
    "auto_scrape": false,
    "auto_subtitles": false,
    "tmdb_api_key": "***",
    "os_api_key": "***",
    "radarr_url": "http://localhost:7878",
    "radarr_api_key": "***",
    "sonarr_url": "http://localhost:8989",
    "sonarr_api_key": "***",
    "llm_provider": "cloud",
    "llm_cloud_url": "https://api.together.xyz/v1/chat/completions",
    "llm_cloud_key": "***",
    "llm_cloud_model": "qwen/qwen2.5-72b-instruct",
    "llm_local_url": "http://host.docker.internal:11434/v1/chat/completions",
    "llm_local_key": "ollama",
    "llm_local_model": "qwen2.5",
    "ai_name": "AI 影音大师",
    "ai_persona": "你是一个专业的 NAS 影音库管理员",
    "expert_archive_rules": "...",
    "master_router_rules": "..."
  },
  "paths": [
    {
      "id": 1,
      "type": "download",
      "path": "/mnt/downloads",
      "category": "movie",
      "enabled": true
    }
  ]
}
```

#### `POST /tasks/settings`

更新系统配置。

**请求体**：`SettingsConfig`

**约束**：
- 同时只能启用 1 个电影媒体库 + 1 个剧集媒体库（1+1 约束）
- 所有 API Key 在后端加密存储

**响应**：`{"message": "配置已保存"}`

#### `POST /tasks/settings/reset`

重置配置为默认值。

**请求体**：

```json
{
  "target": "ai"  // 或 "regex"
}
```

- `target=ai`：重置 AI 规则（`expert_archive_rules` + `master_router_rules`）
- `target=regex`：重置正则规则（`filename_clean_regex` 恢复 15 条默认规则）

**响应**：`{"message": "配置已重置"}`

---

## 四、系统端点（`/api/v1/system`）

### 4.1 `GET /system/stats`

返回媒体库统计数据。

**响应**：`StatsResponse`

```json
{
  "movies": 120,
  "tv_shows": 450,
  "pending": 3,
  "completed": 162
}
```

**字段说明**：

| 字段 | 说明 |
|---|---|
| `movies` | 电影数量（物理文件夹计数，缓存模式）|
| `tv_shows` | 剧集总集数（递归统计视频文件数，缓存模式）|
| `pending` | 待处理任务数（实时读取 `tasks` 表）|
| `completed` | 已完成任务数（实时读取 `tasks` 表）|

**缓存更新时机**：
- 手动点击 Scan 按钮完成后
- 手动点击 Scrape 按钮完成后
- 定时巡逻完成相应步骤后

---

### 4.2 `GET /system/logs`

读取系统日志，支持按标签过滤。

**Query 参数**：

| 参数 | 说明 |
|---|---|
| `tags` | 逗号分隔的标签，如 `SCAN,TMDB,ERROR` |

**支持的标签**：

`SCAN` / `TMDB` / `SUBTITLE` / `ERROR` / `API` / `ORGANIZER` / `ORG` / `CLEAN` / `LLM` / `AI` / `AI-EXEC` / `META` / `DB` / `SECURITY` / `DEBUG`

**响应**：

```json
{
  "logs": [
    {
      "timestamp": "2026-03-11T10:00:00.000",
      "level": "INFO",
      "message": "扫描完成，发现 156 个文件",
      "tag": "SCAN"
    }
  ],
  "source": "/app/data/logs/app.log",
  "total": 1256
}
```

---

## 五、AI 对话端点（`/api/v1/agent`）

### 5.1 `POST /agent/chat`

AI 对话网关，接收用户消息，识别意图，自动触发对应任务。

**请求体**：`ChatRequest`

```json
{
  "message": "帮我下载星际穿越"
}
```

**响应**：`ChatResponse`

```json
{
  "response": "正在为你寻找资源...",
  "action": "DOWNLOAD"
}
```

**意图码说明**：

| 意图码 | 触发动作 | 说明 |
|---|---|---|
| `ACTION_SCAN` | `POST /tasks/scan` | 触发物理扫描 |
| `ACTION_SCRAPE` | `POST /tasks/scrape_all` | 触发全量刮削 |
| `ACTION_SUBTITLE` | `POST /tasks/find_subtitles` | 触发字幕查找 |
| `DOWNLOAD` | 无（AIAgent 内部处理）| 寻猎者引擎已在 agent 内部完成 |
| `None` | 无 | 纯对话或候选展示阶段 |

**处理流程**：

```
POST /agent/chat
  └─► AIAgent.process_message(message)
        ├─► 候选状态检查（从数据库读取）
        ├─► LLM 意图识别（使用 master_router_rules）
        ├─► 生成响应文本（使用 ai_persona）
        └─► 返回 (response_text, action_code)
  └─► 根据 action_code 自动触发后台任务
  └─► 返回 ChatResponse
```

---

## 六、公共端点（`/api/v1/public`）

### 6.1 `GET /public/image`

安全图片代理，通过 `path` 参数代理本地图片文件。

**Query 参数**：

| 参数 | 说明 |
|---|---|
| `path` | 图片物理路径（URL 编码）|

**请求示例**：

```
GET /api/v1/public/image?path=%2Fmnt%2Fstorage%2Fmovies%2Fposter.jpg
```

**响应**：直接返回图片文件内容（`FileResponse`）

**安全防护**：

1. **路径穿越防御**：使用 `Path.resolve()` 消解 `../` 等穿越尝试
2. **OS 自适应黑名单**：
   - Windows：`C:/Windows`, `C:/Users`, `C:/Program Files`
   - Linux：`/etc`, `/root`, `/boot`, `/proc`, `/sys`, `/dev`, `/var/run`
3. **后缀白名单**：仅允许 `.jpg` / `.jpeg` / `.png` / `.webp` / `.gif`
4. **存在性校验**：文件不存在返回 `HTTP 404`

**错误响应**：

| 状态码 | 说明 |
|---|---|
| 400 | 非法的路径编码格式 |
| 403 | 敏感目录访问或非授权文件后缀 |
| 404 | 文件不存在 |

---

## 七、前端交互契约

### 7.1 统一请求封装（`frontend/lib/api.ts`）

所有受保护 API 调用通过 `secureFetch()` + `getHeaders()` 进行：

```typescript
// Token 存储
localStorage.getItem('token')

// Header 注入
headers['Authorization'] = `Bearer ${token}`

// 401 统一处理
if (res.status === 401) {
  window.location.href = '/';  // 重定向到登录页
}
```

### 7.2 图片加载协议（`frontend/components/media/MediaTable.tsx`）

```typescript
const getPosterUrl = (task: Task): string => {
  const posterPath = task.local_poster_path || task.poster_path;
  
  // 远程图片直连
  if (posterPath?.startsWith('http')) {
    return posterPath;
  }
  
  // 本地图片通过代理
  if (posterPath) {
    return `/api/v1/public/image?path=${encodeURIComponent(posterPath)}`;
  }
  
  // 占位图
  return '/placeholder-poster.jpg';
};
```

**交互契约**：

- HTTP(S) URL → 浏览器直接加载，不经过后端
- 本地路径 → 通过 `/api/v1/public/image` 代理，使用 `encodeURIComponent` 编码
- 无路径 → 使用占位图

---

## 八、数据模型

### 8.1 Task

```typescript
interface Task {
  id: number;
  file_path: string;
  file_name?: string;
  media_type: 'movie' | 'tv';
  status: 'pending' | 'scraped' | 'failed' | 'archived' | 'ignored';
  tmdb_id?: number | string;
  imdb_id?: string;
  title?: string;
  year?: number | string;
  poster_path?: string;
  local_poster_path?: string;
  target_path?: string;
  sub_status?: 'pending' | 'scraped' | 'failed' | 'missing';
  season?: number | null;
  episode?: number | null;
  created_at: string;
}
```

### 8.2 SettingsConfig

```typescript
interface SettingsConfig {
  settings: {
    ui_lang: string;
    min_size_mb: number;
    filename_clean_regex: string;
    cron_enabled: boolean;
    cron_interval_min: number;
    auto_process_enabled: boolean;
    auto_scrape: boolean;
    auto_subtitles: boolean;
    tmdb_api_key: string;
    os_api_key: string;
    radarr_url: string;
    radarr_api_key: string;
    sonarr_url: string;
    sonarr_api_key: string;
    llm_provider: string;
    llm_cloud_url: string;
    llm_cloud_key: string;
    llm_cloud_model: string;
    llm_local_url: string;
    llm_local_key: string;
    llm_local_model: string;
    ai_name: string;
    ai_persona: string;
    expert_archive_rules: string;
    master_router_rules: string;
  };
  paths: Array<{
    id?: number;
    type: string;
    path: string;
    category: string;
    enabled?: boolean;
  }>;
}
```

---

## 九、安全基线与最佳实践

### 9.1 "默认拦截，显式豁免" 清单

| 路由 | 鉴权 | 说明 |
|---|---|---|
| `/api/v1/auth/*` | ❌ 豁免 | 登录与初始化流程 |
| `/api/v1/tasks/*` | ✅ 必须 | 任务管理 |
| `/api/v1/system/*` | ✅ 必须 | 系统统计与日志 |
| `/api/v1/agent/*` | ✅ 必须 | AI 对话 |
| `/api/v1/public/image` | ❌ 豁免 | 图片代理（路径安全机制）|
| `/health` | ❌ 豁免 | 健康检查 |

### 9.2 前端调用规范

- ✅ 使用 `lib/api.ts` 作为唯一业务调用入口
- ✅ 所有受保护接口通过 `secureFetch()` + `getHeaders()` 调用
- ✅ 图片加载使用 `getPosterUrl()` 等封装函数
- ❌ 禁止在组件中直接调用 `fetch` 访问受保护端点
- ❌ 禁止硬编码 API 路径

### 9.3 后端开发规范

- ✅ 所有新增业务 API 必须通过 `api_router` 挂载
- ✅ 所有过滤规则必须来自数据库，严禁硬编码
- ✅ 所有 AI 规则必须来自数据库（`expert_archive_rules`、`master_router_rules`）
- ❌ 禁止绕过 `Depends(get_current_user)` 手写鉴权逻辑
- ❌ 禁止在随机 Handler 内重复认证

---

## 十、版本历史

| 版本 | 日期 | 变更内容 |
|---|---|---|
| V1.0 | 2026-03-09 | 初始版本（理想状态）|
| V1.1 | 2026-03-11 | 基于实际代码重构，补充完整 API 端点、数据模型、前后端交互契约 |

---

**文档维护**：本文档由首席系统架构师 & 数据工程师维护。任何 API 变更必须同步更新本文档，保持**文档即架构**的一致性。

---

## 文档信息

| 项目 | 内容 |
|------|------|
| 文档编号 | ARCH-API-005 |
| 版本 | V1.1 |
| 最后更新 | 2026-03-11 |
| 维护者 | Neon Crate 系统架构师 |
| 状态 | 已生效 |

*本文档基于真实代码物理结构编写，任何架构变更必须同步更新本文档，保持文档即架构的一致性。*
