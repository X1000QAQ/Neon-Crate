# lib/api.ts — API 客户端

**文件路径**: `frontend/lib/api.ts`

---

## 职责

封装所有前后端通信，统一处理 JWT 注入、错误解析和断线检测。

---

## 基础请求封装

```typescript
async function request<T>(url, options): Promise<T> {
  const token = localStorage.getItem('token');
  headers['Authorization'] = `Bearer ${token}`;
  
  const res = await fetch(url, { headers, ...options });
  
  // 断线检测
  if (res.status === 0 || res.status >= 500) {
    window.__setLinkDown?.(true);  // 触发 NeuralLinkAlert
  }
  
  if (!res.ok) throw error;
  return res.json();
}
```

所有请求通过 Next.js `next.config.js` 的 rewrite 规则转发：  
`/api/*` → `http://localhost:8000/api/*`

---

## 接口方法速查

### 鉴权

```typescript
api.authStatus()                        // GET /api/v1/auth/status
api.initAuth(username, password)        // POST /api/v1/auth/init
api.login(username, password)           // POST /api/v1/auth/login
```

### 统计 & 日志

```typescript
api.getStats()                          // GET /api/v1/system/stats
api.getSystemLogs(tags?: string)        // GET /api/v1/system/logs?tags=...
```

### 任务管理

```typescript
api.getTasks(params: {
  page?, page_size?, status?,
  media_type?, search?
})                                      // GET /api/v1/tasks
api.retryTask(taskId)                   // POST /api/v1/tasks/{id}/retry
api.deleteTask(taskId)                  // DELETE /api/v1/tasks/{id}
api.deleteBatchTasks(ids: number[])     // POST /api/v1/tasks/delete_batch
api.purgeAllTasks()                     // POST /api/v1/tasks/purge
```

### 后台任务触发

```typescript
api.triggerScan()                       // POST /api/v1/tasks/scan
api.triggerScrapeAll()                  // POST /api/v1/tasks/scrape_all
api.triggerFindSubtitles()              // POST /api/v1/tasks/find_subtitles
```

### 设置

```typescript
api.getSettings()                       // GET /api/v1/tasks/settings
api.updateSettings(config)              // POST /api/v1/tasks/settings
api.resetSettings(target)              // POST /api/v1/tasks/settings/reset
```

### AI 对话

```typescript
api.chat(message: string)               // POST /api/v1/agent/chat
// 返回 { response: string, action?: string }
```

---

## 错误处理

```typescript
// API 错误包含 status 和 body 字段，便于上层 catch 区分
const error = new Error(body?.detail || body?.message || res.statusText);
(error as any).status = res.status;
(error as any).body = body;
throw error;
```
