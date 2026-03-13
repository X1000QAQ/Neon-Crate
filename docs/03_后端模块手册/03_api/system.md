# system — 系统监控端点

**文件路径**: `backend/app/api/v1/endpoints/system.py`  
**路由前缀**: `/api/v1/system`（受保护）+ `/api/v1/public`（图片代理）  
**JWT 保护**: ✅（两组路由均需要）

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/system/stats` | 获取控制台统计数据 |
| `GET` | `/api/v1/system/logs` | 读取系统日志（最近 1000 行）|
| `GET` | `/api/v1/public/image` | 图片代理（本地海报透传）|

---

## GET /system/stats

### 响应体

```json
{
  "movies": 120,
  "tv_shows": 45,
  "pending": 3,
  "completed": 165
}
```

### 数据来源

| 字段 | 来源 | 更新时机 |
|------|------|----------|
| `movies` | `db.get_config("library_movies_count")` | 扫描/刮削任务完成后 |
| `tv_shows` | `db.get_config("library_tv_count")` | 扫描/刮削任务完成后 |
| `pending` | `tasks` 表实时统计 | 每次请求实时查询 |
| `completed` | `tasks` 表实时统计 | 每次请求实时查询 |

`movies` / `tv_shows` 使用缓存模式，由 `_update_library_counts()` 在任务完成后写入，避免频繁扫盘 I/O。

---

## GET /system/logs

### 查询参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `tags` | 逗号分隔的标签过滤 | `SCAN,TMDB,ERROR` |

### 支持的标签

`SCAN` `TMDB` `SUBTITLE` `ERROR` `API` `ORGANIZER` `ORG` `CLEAN` `LLM` `AI` `AI-EXEC` `META` `DB` `SECURITY` `DEBUG`

### 响应体

```json
{
  "logs": [
    {
      "timestamp": "2026-03-12T10:00:00.000",
      "level": "INFO",
      "message": "[SCAN] 扫描完成，新增 5 条任务记录",
      "tag": "SCAN"
    }
  ],
  "source": "/app/data/logs/app.log",
  "total": 1
}
```

日志从文件末尾反向读取，最多返回 1000 行，兼容标准格式和非标准 print 输出。

---

## GET /public/image

### 查询参数

| 参数 | 说明 |
|------|------|
| `path` | URL 编码的本地图片物理路径 |

### 安全防护

1. `Path.resolve()` 处理所有 `../` 路径穿越尝试
2. 动态黑名单（Linux: `/etc`, `/root`, `/proc` 等；Windows: `C:/Windows`, `C:/Users` 等）
3. 后缀名白名单：`.jpg` `.jpeg` `.png` `.webp` `.gif`
4. 文件存在性校验

```
非法后缀 → 403 Forbidden
敏感目录 → 403 Forbidden
路径穿越 → 400 Bad Request
文件不存在 → 404 Not Found
合法请求 → FileResponse
```
