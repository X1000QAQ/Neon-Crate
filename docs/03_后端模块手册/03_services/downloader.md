# Servarr 下载器手册 - `app/services/downloader/servarr.py`

> 路径：`backend/app/services/downloader/servarr.py`

---

## 一、模块概述

**ServarrClient** 对接 Radarr（电影）和 Sonarr（剧集），实现 AI 指令驱动的自动下载。核心设计：TMDB 侦察兵预先获取 TMDB ID，再用 `tmdb:ID` 精准匹配，避免名称模糊匹配误差。

候选选择流程中，若已知 TMDB ID（来自 `_pending_candidates`），可直接传入跳过侦察步骤，节省一次 TMDB 网络请求。

---

## 二、初始化

```python
ServarrClient(db_manager)  # 配置从 DB 动态读取
```

---

## 三、核心方法

### `add_movie(title, year="", tmdb_id=0) -> Dict`

```
步骤 0: 若 tmdb_id > 0，直接构造 tmdb_info 跳过 TMDB 侦察
        否则 _tmdb_recon(title, "movie")  获取真实 TMDB ID
步骤 A: Radarr Lookup  GET /api/v3/movie/lookup?term=tmdb:{id}
步骤 B: Root Folder    GET /api/v3/rootfolder
步骤 C: Quality Profile GET /api/v3/qualityprofile
步骤 D: 查重防御       已在库中则触发补全搜索
步骤 E: 添加          POST /api/v3/movie
步骤 F: 兜底          HTTP 400 + "already been added" → 返回成功
```

**返回：** `{"success": bool, "msg": str, "data": dict}`

### `add_series(title, year="", tmdb_id=0) -> Dict`

流程与 `add_movie` 相同，接口换为 `/api/v3/series/lookup` 和 `/api/v3/series`。
同样支持 `tmdb_id` 参数跳过 TMDB 侦察。

### `_tmdb_recon(name, media_type, year) -> Optional[Dict]`

TMDB 侦察兵（同步）：
- 从 DB 读取 `tmdb_api_key`，调用 `TMDBAdapter.search_movie/tv()`
- 若提供 `year`，优先选择年份匹配的结果
- 返回 `{"tmdbId": int, "title": str, "year": str}` 或 `None`

---

## 四、配置读取

| 配置键 | 说明 |
|---|---|
| `radarr_url` / `radarr_api_key` | Radarr 地址和密钥 |
| `radarr_quality_profile` | 质量档案名称（默认 `Any`）|
| `sonarr_url` / `sonarr_api_key` | Sonarr 地址和密钥 |
| `sonarr_quality_profile` | 质量档案名称（默认 `Any`）|
| `tmdb_api_key` | TMDB API Key（侦察兵使用）|

---

## 五、注意事项

- Radarr/Sonarr 未配置时直接返回失败，不抛异常
- 电影已在库中时自动触发搜索补全命令（`POST /api/v3/command`）
- `_tmdb_recon` 是同步方法，调用开销通常 < 1s，可在 async 函数中直接调用
- 候选选择流程传入 `tmdb_id` 时跳过 TMDB 侦察，避免中文名搜索精度问题（如「蜘蛛侠」误匹配第一个结果而非用户选定的「蜘蛛侠：纵横宇宙」）

---

*最后更新：2026-03-11*
