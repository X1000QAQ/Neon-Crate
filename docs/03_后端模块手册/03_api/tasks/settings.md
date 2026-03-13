# settings_router — 系统配置路由

**文件路径**: `backend/app/api/v1/endpoints/tasks/settings_router.py`  
**依赖注入**: `db: DbDep`

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/tasks/settings` | 获取完整系统配置 |
| `POST` | `/tasks/settings` | 更新系统配置 |
| `POST` | `/tasks/settings/reset` | 重置 AI 或 Regex 配置为默认值 |

---

## GET /tasks/settings

返回 `SettingsConfig` 模型，包含 `settings` 对象和 `paths` 数组。

---

## POST /tasks/settings

### 请求体

```json
{
  "settings": { "tmdb_api_key": "...", "cron_enabled": true, ... },
  "paths": [
    { "type": "download", "path": "/downloads", "category": "mixed", "enabled": true },
    { "type": "library", "path": "/media/movies", "category": "movie", "enabled": true },
    { "type": "library", "path": "/media/tv", "category": "tv", "enabled": true }
  ]
}
```

### 1+1 绝对约束校验

保存前强制校验：已启用的媒体库路径中，**必须恰好有 1 个电影库和 1 个剧集库**。

| 违规情况 | HTTP 响应 |
|----------|----------|
| 超过 1 个电影库或剧集库 | 400 Bad Request |
| 缺少电影库 | 400 Bad Request |
| 缺少剧集库 | 400 Bad Request |
| 全部通过 | 写盘，返回 200 |

---

## POST /tasks/settings/reset

```json
// 请求体
{ "target": "ai" }   // 或 "regex"

// 响应
{ "success": true, "message": "AI 配置已重置为工业级默认值" }
```

| target | 重置内容 |
|--------|----------|
| `"ai"` | `ai_name` / `ai_persona` / `expert_archive_rules` / `master_router_rules` |
| `"regex"` | `filename_clean_regex`（15 条工业默认规则）|
