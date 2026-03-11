# 扫描引擎手册 - `app/services/scraper/`

> 路径：`backend/app/services/scraper/engine.py` + `cleaner.py` + `filters.py`

> **重构说明（2026-03-11）**：`MediaCleaner` 完全去除硬编码正则，改为从数据库 `filename_clean_regex` 动态加载。`ScanEngine` 新增 `db_manager` 参数。架构与 AI 人格设定完全一致：数据库是唯一真相源。

---

## 一、`ScanEngine`

### 初始化

```python
ScanEngine(max_workers=4, min_size_mb=50, db_manager=None)
```

| 参数 | 说明 |
|---|---|
| `max_workers` | 并发线程数 |
| `min_size_mb` | 最小文件体积（MB），设 0 可扫描测试空文件 |
| `db_manager` | 传入后 `MediaCleaner` 从数据库加载正则 |

### 核心方法

#### `scan_directory(directory, recursive=True) -> List[Dict]`

```python
{
    'path': str, 'file_name': str, 'size': int,
    'clean_name': str, 'year': int|None,
    'is_tv': bool, 'season': int|None, 'episode': int|None
}
```

### 防护机制

| 防护 | 实现 |
|---|---|
| 软链接死循环 | `os.walk(followlinks=False)` |
| 超深目录 | `MAX_SCAN_DEPTH=5`，超过则剪枝 |
| NAS 系统目录 | 跳过 `/@eadir/`、`.deletedbytmm`、隐藏目录 |
| 样片文件 | 跳过含 `sample`/`样片` 的目录和文件 |
| 并发去重 | `Set[str]` 路径去重 |

---

## 二、`MediaCleaner`（全量数据库驱动）

### 架构说明

`MediaCleaner` 是纯执行层（苦力），不硬编码任何过滤正则。**`filename_clean_regex` 是系统唯一正则真相源。**

```
数据库 filename_clean_regex
  └─► _load_patterns()   # 启动时编译为 pattern 列表
        └─► clean_name() # 逐条执行 sub(' ')
```

### 初始化

```python
MediaCleaner(db_manager=None)
```

- `db_manager=None`：仅执行符号清理，不加载正则规则（无数据库场景下的降级模式）
- `db_manager=db`：从数据库读取 `filename_clean_regex` 并编译为 pattern 列表

### 固定内置正则（结构化提取专用，不参与过滤）

| 常量 | 用途 |
|---|---|
| `_YEAR_PATTERN` | 年份提取，支持 `(2024)`、`.2024.`、裸年份 |
| `_SEASON_EPISODE_PATTERNS` | S01E01 / Season格式 / 1x01 / EP01 / 第01集 |
| `_ANIME_EPISODE_PATTERN` | 动漫格式 `- 28 [` |

这些正则仅用于**提取**季号/集号/年份，不用于文件名过滤，**不受 RegexLab 管理**。

### `clean_name(filename) -> str` 清洗步骤

1. 去除文件扩展名
2. 去除首部方括号组名（`[HbT]`、`[SubsPlease]` 等，20字以内）
3. 去除所有剩余方括号及其内容（兜底）
4. 执行数据库过滤正则（逐条 `sub(' ')`）
5. 中文冒号 → 英文冒号
6. 下划线/点/横线 → 空格
7. 清理多余空格 + 首尾特殊符号

### 其他方法

| 方法 | 说明 |
|---|---|
| `extract_year(filename)` | 提取年份，验证范围 1900-2099 |
| `extract_season_episode(filename)` | 提取季/集，返回 `(season, episode)` |
| `is_tv_show(filename)` | 是否含季集信息 |
| `is_advertisement(filename)` | 是否广告文件 |
| `clean_and_extract(filename)` | 一站式返回完整结构化字典 |

---

## 三、数据库正则规则格式

`filename_clean_regex` 默认 15 条规则，每行一条，`#` 开头为注释：

| # | 用途 |
|---|---|
| 1 | 分辨率过滤（1080p/4K/BluRay...）|
| 2 | 编码格式过滤（x264/HEVC/AAC...）|
| 3 | 方括号技术标签过滤（含压制组关键词）|
| 4 | 花括号标签过滤 |
| 5 | 广告词过滤 |
| 6 | 音视频特性过滤（HDR/10bit/IMAX...）|
| 7 | 语言标签过滤（中英/CHT/Cantonese...）|
| 8 | 制作组后缀过滤（`-TEAM` 末尾）|
| 9 | 年份过滤（片名中清除）|
| 10-14 | 季集标签过滤（片名中清除）|
| 15 | 动漫番剧集数过滤 |

用户可在前端 RegexLab 自由增删，重启后端生效。一键重置：`POST /tasks/settings/reset {"target": "regex"}`

---

## 四、调用链

### 扫描链

```
POST /tasks/scan
  └─► ScanEngine(db_manager=db)
        └─► MediaCleaner(db_manager=db_manager)
              └─► _load_patterns()  # 编译数据库规则
        └─► scan_directory()
              └─► _process_single_file()
                    └─► MediaFilter + MediaCleaner.clean_and_extract()
  └─► db_manager.insert_task()  # 去重入库
```

### 刮削链

```
POST /tasks/scrape_all
  └─► perform_scrape_all_task_sync()
        └─► MediaCleaner(db_manager=db).clean_name(raw_filename)  # 前置清洗
              └─► 数据库 filename_clean_regex（全局唯一真相源）
        └─► ai_agent.ai_identify_media(cleaned_name)
        └─► scraper.search_tv/movie(query)
              └─► TMDB 精确匹配（original_name/name == query）
              └─► 宽松匹配（去末尾集号后匹配）
        └─► 归档路径构建
              └─► season_num 从路径 Season XX 补充
        └─► db.update_task_title_year(season=season_num)  # 季号回写
```

---

## 五、注意事项

- **严禁**在 `cleaner.py`、`engine.py`、`tasks.py` 中硬编码任何过滤正则，所有规则必须来自数据库
- `_YEAR_PATTERN`、`_SEASON_EPISODE_PATTERNS` 等结构化提取正则是固定工具，不属于「过滤规则」，保留硬编码是正确的
- 扫描时 `season` 从文件名提取，归档时从路径目录名补充校正，两次机会确保季号准确

---

*最后更新：2026-03-11*
