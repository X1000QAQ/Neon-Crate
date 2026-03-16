# 双轨隔离 NFO 本地真理引擎 — 侦察报告 v2

**文档编号**：DEV-RECON-005-v2  
**版本**：v2.0.0  
**日期**：2026-03-15  
**状态**：✅ 侦察完成，待确认后实施  
**GitNexus 基准**：commit `da6f881`，✅ up-to-date

---

## 一、TMM 真实 NFO 样本解析结论

### `movie.nfo`（小丑回魂，TMM 3.1.16.1）关键字段

```xml
<tmdbid>346364</tmdbid>
<uniqueid default="false" type="tmdb">346364</uniqueid>
<uniqueid default="true"  type="imdb">tt1396484</uniqueid>
<id>tt1396484</id>
```

### `tvshow.nfo`（怪奇物语）关键字段

```xml
<tmdbid>66732</tmdbid>
<imdbid>tt4574334</imdbid>
```

### TMM 格式矩阵

| 字段 | movie.nfo | tvshow.nfo | 当前 Neon 解析器 |
|------|-----------|------------|------------------|
| tmdb_id | `<tmdbid>` ✅ | `<tmdbid>` ✅ | 只读 `<tmdbid>` ✅ 已覆盖 |
| imdb_id | **无** `<imdbid>`，在 `<uniqueid type="imdb">` 和 `<id>` 中 | `<imdbid>` ✅ | 只读 `<imdbid>` ❌ 电影 imdb 丢失 |

**关键发现**：TMM `movie.nfo` 没有 `<imdbid>` 直接节点，imdb_id 藏在 `<uniqueid type="imdb">` 和 `<id>` 里。当前解析器会丢失电影的 imdb_id。

---

## 二、双轨隔离原则

| 轨道 | 触发时机 | 信任来源 | 禁止操作 |
|------|---------|---------|----------|
| 🚂 自动刮削轨 | `perform_scrape_all_task_sync` | **本地 NFO 为绝对真理** | 禁止调用 AI Agent / TMDB 搜索 |
| 🚀 手动核武轨 | 用户点击 📄 后 `manual_rebuild` | **人类选择为最高意志** | 禁止读取本地 NFO，强制走 TMDB 网络 |

---

## 三、现状审计

### 3.1 自动刮削轨 — 已实现 ✅

- ✅ 季目录回溯（`Season X` 正则）
- ✅ `movie.nfo` / `tvshow.nfo` 寻址
- ✅ `<tmdbid>` 直接节点提取
- ✅ `<imdbid>` 直接节点提取（tvshow 正常，movie 丢失）
- ✅ DB 双表更新 + 短路 `continue`

### 3.2 自动刮削轨 — 缺失项 ❌

| 缺失项 | 影响 |
|--------|------|
| `<uniqueid type="tmdb">` fallback | TMM movie 若无 `<tmdbid>` 则短路失效 |
| `<uniqueid type="imdb">` + `<id>` fallback | TMM movie.nfo imdb_id 丢失 |
| 同名 `.nfo` 寻址（Plex 风格）| `小丑回魂 (2017).nfo` 无法被找到 |
| 独立 `nfo_parser.py` 模块 | 代码内联，维护困难 |

### 3.3 手动核武轨 — 已符合双轨原则 ✅

`manual_rebuild` 完全不读本地 NFO，符合隔离原则：
- ✅ 只信任前端传来的 `tmdb_id` 和 DB 已有值
- ✅ `nuclear_reset=True` 时 `_nuclear_clean_directory` 删除所有非视频文件（含旧 NFO）
- **无需修改** 此轨道

### 3.4 TMM 兼容性输出 — 缺失项 ❌

`MetadataManager._build_movie_nfo` / `_build_tv_nfo`：
- ✅ 已有 `<tmdbid>` + `<imdbid>`
- ❌ 缺少 `<uniqueid type="tmdb" default="true">`
- ❌ 缺少 `<uniqueid type="imdb">`

---

## 四、`nfo_parser.py` 核心代码片段

### 片段 A：`parse_nfo()` tmdb_id + imdb_id 提取

```python
def parse_nfo(file_path: str) -> Dict[str, Optional[str]]:
    result = {"tmdb_id": None, "imdb_id": None,
              "title": None, "year": None, "plot": None}
    try:
        root = ET.parse(file_path).getroot()

        result["title"] = (root.findtext("title") or "").strip() or None
        result["year"]  = (root.findtext("year")  or "").strip() or None
        result["plot"]  = (root.findtext("plot")  or "").strip() or None

        # tmdb_id: <tmdbid> → <uniqueid type="tmdb">
        tmdb_id = (root.findtext("tmdbid") or "").strip()
        if not tmdb_id:
            for uid in root.findall("uniqueid"):
                if (uid.get("type") or "").lower() == "tmdb":
                    tmdb_id = (uid.text or "").strip()
                    if tmdb_id: break
        result["tmdb_id"] = tmdb_id or None

        # imdb_id: <imdbid> → <uniqueid type="imdb"> → <id> (tt开头)
        imdb_id = (root.findtext("imdbid") or "").strip()
        if not imdb_id:
            for uid in root.findall("uniqueid"):
                if (uid.get("type") or "").lower() == "imdb":
                    imdb_id = (uid.text or "").strip()
                    if imdb_id: break
        if not imdb_id:
            _id = (root.findtext("id") or "").strip()
            if _id.lower().startswith("tt"):
                imdb_id = _id
        result["imdb_id"] = imdb_id or None

    except ET.ParseError as e:
        logger.warning(f"[NfoParser] XML 解析失败: {file_path} - {e}")
    except Exception as e:
        logger.warning(f"[NfoParser] 未知错误: {file_path} - {e}")
    return result
```

### 片段 B：`find_nfo()` 剧集向上寻址

```python
_SEASON_RE = re.compile(r'^(Season|S)\s*\d+$|^Specials$', re.IGNORECASE)

def find_nfo(video_path: str) -> Optional[str]:
    p = Path(video_path)
    d = p.parent

    # Step 1: 同级目录
    for name in ["movie.nfo", "tvshow.nfo", f"{p.stem}.nfo"]:
        c = d / name
        if c.is_file(): return str(c)

    # Step 2: Season 子目录 → 回溯父目录
    if _SEASON_RE.match(d.name):
        parent = d.parent
        for name in ["tvshow.nfo", "movie.nfo"]:
            c = parent / name
            if c.is_file(): return str(c)

    return None
```

**场景演示**：
```
输入: /storage/tv/Stranger Things (2016)/Season 1/S01E01.mkv
Step 1: /Season 1/movie.nfo → 不存在
        /Season 1/tvshow.nfo → 不存在
        /Season 1/S01E01.nfo → 不存在
Step 2: "Season 1" 命中正则 → 回溯
        /Stranger Things (2016)/tvshow.nfo → ✅ 命中！
```

---

## 五、`generate_nfo` TMM 兼容性补充

在 `_build_movie_nfo` 和 `_build_tv_nfo` 写入 `<tmdbid>` 之后补充：

```python
# TMM 兼容：写入 <uniqueid> 节点
tmdb_val = str(_safe_get(details, "id", default=""))
if tmdb_val:
    uid_tmdb = ET.SubElement(root, "uniqueid")
    uid_tmdb.set("type", "tmdb")
    uid_tmdb.set("default", "true")
    uid_tmdb.text = tmdb_val

imdb_val = _safe_get(details, "external_ids", "imdb_id", default="")
if imdb_val:
    uid_imdb = ET.SubElement(root, "uniqueid")
    uid_imdb.set("type", "imdb")
    uid_imdb.text = imdb_val
```

---

## 六、完整修改点清单（3 个文件）

| 文件 | 变更内容 | 状态 |
|------|---------|------|
| `services/metadata/nfo_parser.py` | **新建**：`find_nfo()` + `parse_nfo()`，全兼容 TMM | 待新建 |
| `api/v1/endpoints/tasks/scrape_task.py` | 内联 NFO 块替换为调用 `parse_nfo()`，补充 imdb_id fallback | 待修改 |
| `services/metadata/metadata_manager.py` | `_build_movie_nfo` + `_build_tv_nfo` 补充 `<uniqueid>` 节点 | 待修改 |

**`manual_rebuild` 无需修改** — 已符合双轨隔离原则。

---

## 七、实施前确认清单

- [ ] 确认：`<id>` 字段作为 imdb_id fallback（仅 tt 开头时采用）的策略正确
- [ ] 确认：`_build_movie_nfo` 中 `<uniqueid type="tmdb" default="true">` 还是 `default="false"`（TMM movie 样本中 tmdb 为 false，imdb 为 true）
- [ ] 确认：内联 NFO 块是否完全替换为 `parse_nfo()` 调用，还是保留内联仅补充 uniqueid 支持

---

*Neon Crate 开发团队 | DEV-RECON-005-v2 | 2026-03-15*  
*基于 GitNexus 图谱审计 (commit da6f881) + TMM 实战 NFO 样本精读*
