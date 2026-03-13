# scraper — 扫描引擎服务

**目录**: `backend/app/services/scraper/`

---

## 模块组成

| 文件 | 类 | 职责 |
|------|----|------|
| `engine.py` | `ScanEngine` | 并发目录扫描 + 文件过滤 |
| `cleaner.py` | `MediaCleaner` | 文件名清洗 + 结构化信息提取 |
| `filters.py` | `MediaFilter` | 体积过滤（50MB 门槛）|

---

## ScanEngine

### 初始化

```python
engine = ScanEngine(
    max_workers=4,        # 并发线程数
    min_size_mb=50,       # 最小文件体积（MB）
    db_manager=db         # 用于加载自定义正则规则
)
```

### 核心方法

```python
engine.scan_directory(directory: str, recursive: bool = True) -> List[Dict]
engine.scan_multiple_directories(directories: List[str]) -> List[Dict]
```

### 返回字段

```python
{
    "path": "/downloads/Dune.2021.mkv",
    "file_name": "Dune.2021.mkv",
    "size": 15728640000,
    "clean_name": "Dune",
    "year": 2021,
    "is_tv": False,
    "season": None,
    "episode": None
}
```

### 防护机制

| 机制 | 实现 |
|------|------|
| 软链接死循环 | `followlinks=False` |
| 超深目录 | `MAX_SCAN_DEPTH = 5`，超过则剪枝 |
| 隐藏目录 | 跳过 `/@eadir/`、`.deletedbytmm`、`/.` |
| 样片过滤 | 跳过 `sample` 目录和文件名含 `sample` 的文件 |
| 去重 | 基于文件路径 Set 去重 |

---

## MediaCleaner

### 初始化

```python
cleaner = MediaCleaner(db_manager=db)  # db=None 时仅执行符号清理
```

正则规则从数据库 `filename_clean_regex` 字段加载，用户可通过前端 RegexLab 增删，保存后立即生效。

### 核心方法

```python
cleaner.clean_name(filename) -> str              # 剥离噪声标签
cleaner.extract_year(filename) -> Optional[int]  # 提取年份
cleaner.extract_season_episode(filename) -> Tuple[Optional[int], Optional[int]]
cleaner.is_tv_show(filename) -> bool
cleaner.is_advertisement(filename) -> bool
cleaner.clean_and_extract(filename) -> dict       # 一站式处理
```

### clean_name 处理流程

```
1. 去文件扩展名
2. 去首部方括号组名（[HbT]、[SubsPlease] 等）
3. 去剩余所有方括号内容
4. 执行数据库过滤正则（顺序替换）
5. 中文冒号 → 英文冒号
6. 下划线/点/横线 → 空格
7. 清理多余空格，修剪首尾特殊字符
```

### clean_and_extract 返回值

```python
{
    "clean_name": "Attack on Titan",
    "year": 2013,
    "season": 3,
    "episode": 10,
    "is_tv": True,
    "is_ad": False
}
```

---

## MediaFilter

```python
filter = MediaFilter(min_size_mb=50)
filter.check_file_size(file_path) -> bool  # False = 文件过小
```

在 `ScanEngine._process_single_file()` 中作为第一道关卡使用。
