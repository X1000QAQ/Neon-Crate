# metadata — TMDB 元数据服务

**目录**: `backend/app/services/metadata/`

---

## 模块组成

| 文件 | 类 | 职责 |
|------|----|------|
| `adapters.py` | `TMDBAdapter` | TMDB API 搜索与详情获取 |
| `metadata_manager.py` | `MetadataManager` | NFO 生成 + 海报/Fanart 下载 |

---

## TMDBAdapter

### 初始化

```python
tmdb = TMDBAdapter(api_key="your-tmdb-key")
```

所有方法底层均通过 `http_utils.http_get_with_retry()` 发起请求，自带 3 次指数退避重试。

### 方法速查

```python
tmdb.search_movie(query: str, year: Optional[str] = None) -> List[Dict]
tmdb.search_tv(query: str, year: Optional[str] = None) -> List[Dict]
tmdb.get_movie_details(tmdb_id: str) -> Optional[Dict]
tmdb.get_tv_details(tmdb_id: str) -> Optional[Dict]
tmdb.get_external_ids(tmdb_id: str, media_type: str) -> Dict[str, str]
```

### 搜索参数

| 参数 | 说明 |
|------|------|
| `language` | `zh-CN`（优先返回中文数据）|
| `include_adult` | `false` |
| `primary_release_year` | 电影年份过滤 |
| `first_air_date_year` | 剧集年份过滤 |

---

## MetadataManager

### 初始化

```python
meta = MetadataManager(tmdb_api_key="your-key")
```

### 方法速查

```python
meta.generate_nfo(
    tmdb_id, media_type, output_path,
    title=None, year=None
) -> bool

meta.download_poster(
    tmdb_id, media_type, output_dir,
    title=None
) -> Optional[str]   # 返回本地路径或 None

meta.download_fanart(
    tmdb_id, media_type, output_dir,
    title=None
) -> Optional[str]
```

### NFO 格式

生成符合 **Jellyfin / Emby / Plex** 标准的 XML：
- 电影：`movie.nfo`，根元素 `<movie>`
- 剧集：`tvshow.nfo`，根元素 `<tvshow>`
- 包含字段：title、plot、year、tmdbid、imdbid、rating、genres、actors（前10）、director

### 安全机制

- `_validate_path(target, base)` — 所有写入路径通过 `Path.resolve().relative_to()` 校验，防路径穿越
- 下载失败不抛出异常，返回 `None`，不影响整体归档流程
- 图片下载使用 `http_get_with_retry(timeout=30.0)` 支持大文件超时

### 辅助函数

```python
_safe_get(data, *keys, default="")  # 链式 .get()，杜绝 KeyError
_validate_path(target_path, allowed_base)  # 路径防穿越校验
```
