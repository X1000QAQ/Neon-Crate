# 元数据服务手册 - `app/services/metadata/`

> 路径：`backend/app/services/metadata/adapters.py` + `metadata_manager.py`

---

## 一、模块概述

元数据双引擎：
- **`TMDBAdapter`**：TMDB API 封装，搜索电影/剧集，获取详情和外部 ID
- **`MetadataManager`**：元数据工厂，生成 NFO 文件、下载海报和 Fanart

---

## 二、`TMDBAdapter`

```python
TMDBAdapter(api_key: str)
```

| 方法 | 说明 |
|---|---|
| `search_movie(query, year)` | 搜索电影 |
| `search_tv(query, year)` | 搜索剧集 |
| `get_movie_details(tmdb_id)` | 获取电影详情（含演职员）|
| `get_tv_details(tmdb_id)` | 获取剧集详情 |
| `get_external_ids(tmdb_id, media_type)` | 获取 IMDB ID 等外部 ID |

**429 限流重试：** 最多重试 3 次，指数退避 2s → 4s → 8s。

---

## 三、`MetadataManager`

```python
MetadataManager(tmdb_api_key: str)
```

### `generate_nfo(tmdb_id, media_type, output_path, title, year) -> bool`

生成符合 Jellyfin/Emby/Plex 标准的 NFO XML 文件，包含标题、剧情、评分、演职员、海报、Fanart 等字段。

### `download_poster(tmdb_id, media_type, output_dir, title) -> Optional[str]`

下载 TMDB 海报（原图质量），保存为 `{output_dir}/poster.jpg`。失败不抛异常，返回 `None`。

### `download_fanart(tmdb_id, media_type, output_dir, title) -> Optional[str]`

下载背景图（w1280），保存为 `{output_dir}/fanart.jpg`。

### 路径安全

所有文件写入前经过 `_validate_path()` 校验，`Path.resolve()` 防御 `../` 路径穿越。

---

## 四、调用链

```
POST /tasks/scrape_all
  └─► MetadataManager(tmdb_api_key)
        ├─► TMDBAdapter.search_movie/tv()
        ├─► generate_nfo()
        ├─► download_poster()
        └─► download_fanart()
```

---

## 五、注意事项

- NFO 使用 `xml.dom.minidom` 格式化输出，符合 Jellyfin 解析要求
- 海报/Fanart 下载失败不影响 NFO 生成，各步骤独立容错
- TMDB 返回数据缺少 `id` 字段时返回 `EMPTY_DETAIL` 空结果，不返回 `None`

---

*最后更新：2026-03-11*
