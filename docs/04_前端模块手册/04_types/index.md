# types/index.ts — TypeScript 类型定义

**文件路径**: `frontend/types/index.ts`

---

## 接口速查

### Task — 媒体任务

```typescript
export interface Task {
  id: number;
  file_path: string;
  file_name?: string;
  media_type: 'movie' | 'tv';
  status: 'pending' | 'scraped' | 'failed' | 'archived' | 'ignored';
  tmdb_id?: number;
  imdb_id?: string;
  title?: string;
  year?: number;
  poster_path?: string;
  local_poster_path?: string;
  target_path?: string;
  sub_status?: 'pending' | 'scraped' | 'failed' | 'missing';
  season?: number | null;
  episode?: number | null;
  created_at: string;
}
```

---

### TasksResponse — 任务列表响应

```typescript
export interface TasksResponse {
  tasks: Task[];
  total: number;
  page: number;
  page_size: number;
}
```

与后端 `GET /tasks` 响应体完全对齐（2026-03-12 修复后）。

---

### StatsResponse

```typescript
export interface StatsResponse {
  movies: number;
  tv_shows: number;
  pending: number;
  completed: number;
}
```

---

### ChatMessage / ChatResponse

```typescript
export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatResponse {
  response: string;
  action?: string;  // ACTION_SCAN | ACTION_SCRAPE | ACTION_SUBTITLE | DOWNLOAD | null
}
```

---

### LogEntry

```typescript
export interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG';
  message: string;
  tag?: string;
}
```

---

### SettingsConfig

```typescript
export interface SettingsConfig {
  settings: {
    ui_lang: string;                // 'zh' | 'en'
    min_size_mb: number;
    filename_clean_regex: string;
    cron_interval_min: number;
    cron_enabled: boolean;
    auto_process_enabled: boolean;  // 前端 UI 专用，后端忽略
    auto_scrape: boolean;
    auto_subtitles: boolean;
    tmdb_api_key: string;
    os_api_key: string;
    // Radarr / Sonarr
    radarr_url: string; radarr_api_key: string;
    sonarr_url: string; sonarr_api_key: string;
    // LLM
    llm_provider: string;
    llm_cloud_url: string; llm_cloud_key: string; llm_cloud_model: string;
    llm_local_url: string; llm_local_key: string; llm_local_model: string;
    // AI 人格
    ai_name: string; ai_persona: string;
    expert_archive_rules: string; master_router_rules: string;
  };
  paths: Array<{
    id?: number;
    type: string;      // 'download' | 'library'
    path: string;
    category: string;  // 'movie' | 'tv' | 'mixed'
    enabled?: boolean;
  }>;
}
```

---

### 鉴权相关

```typescript
export interface AuthStatusResponse { initialized: boolean; message: string; }
export interface TokenResponse { access_token: string; token_type: string; username: string; }
```

---

## 前后端类型对齐状态

| 字段 | 前端类型 | 后端类型 | 状态 |
|------|---------|---------|------|
| `Task.media_type` | `'movie'\|'tv'` | `str` | ✅ |
| `Task.tmdb_id` | `number?` | `Optional[int]` | ✅ |
| `TasksResponse` | `{tasks,total,page,page_size}` | 同上 | ✅ |
| `SettingsConfig.auto_process_enabled` | `boolean` | **不存在**（前端专用）| ⚠️ 前端专用字段 |
