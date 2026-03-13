# downloader — Servarr 下载器

**文件路径**: `backend/app/services/downloader/servarr.py`  
**核心类**: `ServarrClient`

---

## 职责

对接 Radarr（电影）和 Sonarr（剧集），将影片加入自动下载队列。

---

## 初始化

```python
servarr = ServarrClient(db_manager=db)
# 从数据库动态读取 radarr_url/key 和 sonarr_url/key
```

---

## 方法速查

```python
result = await servarr.add_movie(title: str, year: str = "") -> dict
result = await servarr.add_series(title: str, year: str = "") -> dict
```

**返回值**：

```python
# 成功
{"success": True, "data": {"title": "Dune"}, "msg": ""}
# 已在队列
{"success": False, "data": {"status": "exists", "title": "Dune"}, "msg": "..."}
# 失败
{"success": False, "data": {}, "msg": "连接 Radarr 失败: ..."}
```

---

## 调用链路

```
AIAgent (DOWNLOAD 意图)
  ├── 模糊片名 → _tmdb_search_candidates() → 展示候选列表
  │     用户选择后 → 直接调用 ServarrClient（携带 tmdb_id）
  └── 明确片名 → ServarrClient.add_movie/series()
        └── Radarr POST /api/v3/movie
            Sonarr POST /api/v3/series
```

---

## 配置依赖

| 配置键 | 说明 |
|--------|------|
| `radarr_url` | Radarr 服务地址（如 `http://localhost:7878`）|
| `radarr_api_key` | Radarr API Key |
| `sonarr_url` | Sonarr 服务地址 |
| `sonarr_api_key` | Sonarr API Key |

均存储于数据库，通过 `db.get_config()` 动态读取。
