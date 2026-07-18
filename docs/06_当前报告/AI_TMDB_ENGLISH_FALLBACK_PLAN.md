# AI 语义识别 + TMDB 搜索英文降级增强方案

## 问题诊断

### 当前现象

```log
[42][INFO][AI] 调用 AI Agent 语义分析: raw='Silver.Medalist.2009.1080p.BluRay.DTS.x265-10bit-HDS.mkv'
[43][INFO]✅ [LLM] cloud(Qwen/Qwen3-235B-A22B-Instruct-2507-tput) 引擎响应成功 | 耗时 4090ms
[44][ERROR][AI] 引擎不可用或识别彻底失败，触发 Fail-Fast: ai_semantic_low_confidence: confidence=0.3

[46][INFO][AI] 调用 AI Agent 语义分析: raw='The.Lychee.Road.2025.2160p.60fps.HQ.WEB-DL.HEVC.10bit.DV.DTS5.1.4Audios-QHstudIo.mp4'
[47][INFO]✅ [LLM] cloud(Qwen/Qwen3-235B-A22B-Instruct-2507-tput) 引擎响应成功 | 耗时 4355ms
[48][ERROR][AI] 引擎不可用或识别彻底失败，触发 Fail-Fast: confidence=0.85
```

### 根因分析

**问题 1：AI 置信度过滤过于严格**

当前系统对 `confidence < 某阈值` 的识别结果直接触发 Fail-Fast，即使 `confidence=0.85` 这样的高置信度结果也被拒绝。

**问题 2：TMDB 搜索不兼容点分隔文件名**

- 文件名格式：`The.Lychee.Road.2025` / `Silver.Medalist.2009`
- AI 可能输出：`The.Lychee.Road` 或 `The Lychee Road`
- TMDB API：仅接受空格分隔的自然语言查询，点号会导致零结果

**问题 3：缺少英文降级搜索链路**

当前 TMDB 搜索逻辑（`adapters.py`）已有三梯队降级：

```text
Title + Year → Title（无 Year）→ 截断 Title（无 Year）
```

但缺少：

```text
英文原名兜底搜索
```

对于中文电影使用英文国际片名（如《荔枝之路》→ `The Lychee Road`），TMDB 上可能只能用英文搜索到。

---

## 解决方案设计

### 核心策略

**分层兜底 + 文本归一化 + 英文降级**

```text
AI 识别
  ├─ 置信度 ≥ 0.7 → 进入 TMDB 搜索
  │   ├─ 查询前：点号转空格归一化（The.Lychee.Road → The Lychee Road）
  │   ├─ 第一轮：AI 返回的 query（中文或英文）+ Year
  │   ├─ 第二轮：AI 返回的 query（去 Year）
  │   ├─ 第三轮：截断 query（去副标题）
  │   └─ **第四轮（新增）：从原始文件名提取英文片名 + Year**
  │
  └─ 置信度 < 0.7 → Fail-Fast（维持现有安全边界）
```

---

## 实施计划

### 第一阶段：放宽置信度阈值（建议修正值）

**目标文件**：`backend/app/api/v1/endpoints/tasks/scrape_task.py`

**当前逻辑**（推测）：

```python
confidence = ai_result.get("confidence", 0.0)
if confidence < 某阈值:  # 可能是 0.9 或硬编码条件
    logger.error(f"[AI] 触发 Fail-Fast: confidence={confidence}")
    return
```

**修改方案**：

将置信度阈值从 `0.9` 降低到 `0.7`，允许更多合理识别结果进入 TMDB 搜索链路。

```python
CONFIDENCE_THRESHOLD = 0.7  # 新增常量

confidence = ai_result.get("confidence", 0.0)
if confidence < CONFIDENCE_THRESHOLD:
    logger.error(f"[AI] 识别置信度过低，触发 Fail-Fast: confidence={confidence}")
    # 标记任务为 failed，记录原因
    db.update_task_status(task_id, "failed", f"ai_semantic_low_confidence: confidence={confidence}")
    return
```

**验证指标**：

- `confidence=0.85` 的识别结果不再被 Fail-Fast
- `confidence=0.3` 的识别结果仍然被拒绝

---

### 第二阶段：TMDB 查询预处理（点号转空格）

**目标文件**：`backend/app/services/metadata/adapters.py`

**修改位置**：`search_media()` / `search_movie()` / `search_tv()` 方法

**当前代码**（推测）：

```python
def search_media(self, query: str, media_type: str = "movie", year: Optional[str] = None):
    params = {
        "api_key": self.api_key,
        "query": query,  # 直接使用 AI 返回的 query
        ...
    }
```

**修改方案**：

在所有 TMDB 搜索入口统一做查询预处理。

```python
def _normalize_query(self, query: str) -> str:
    """
    TMDB 查询预处理：点号转空格

    TMDB API 不接受点分隔的文件名格式，需归一化为自然语言。

    Examples:
        The.Lychee.Road       → The Lychee Road
        Silver.Medalist.2009  → Silver Medalist 2009
        攻壳机动队.Stand.Alone  → 攻壳机动队 Stand Alone
    """
    normalized = query.replace(".", " ").strip()
    # 去除多余空格
    normalized = " ".join(normalized.split())
    return normalized

def search_media(self, query: str, media_type: str = "movie", year: Optional[str] = None):
    # 查询预处理
    normalized_query = self._normalize_query(query)
    logger.info(f"[TMDB] 查询归一化: '{query}' → '{normalized_query}'")

    params = {
        "api_key": self.api_key,
        "query": normalized_query,  # 使用归一化后的查询
        ...
    }
```

**适用范围**：

- `search_media()`
- `search_movie()`
- `search_tv()`

---

### 第三阶段：英文降级搜索（核心增强）

**目标文件**：`backend/app/api/v1/endpoints/tasks/scrape_task.py`

**插入位置**：TMDB 三梯队搜索全部失败后

**实现逻辑**：

```python
def _extract_english_title(filename: str) -> Optional[str]:
    """
    从文件名中提取英文片名（兜底识别）

    策略：
    1. 匹配连续英文单词 + 可选年份模式
    2. 过滤纯数字、技术参数（1080p / BluRay / x265 等）
    3. 返回归一化后的英文片名

    Examples:
        Silver.Medalist.2009.1080p.BluRay...    → Silver Medalist
        The.Lychee.Road.2025.2160p.60fps...     → The Lychee Road
        [组名]中文片名.English.Title.2023.mp4    → English Title
    """
    import re

    # 去除组名标签、路径和扩展名
    base = filename.split('/')[-1]  # 去除路径
    base = re.sub(r'^\[.*?\]', '', base)  # 去除组名 [xxx]
    base = re.sub(r'\.(mkv|mp4|avi)$', '', base, flags=re.I)  # 去除扩展名

    # 匹配英文单词序列（在遇到技术参数前停止）
    # 模式：连续的"单词."组合，直到遇到分辨率/编码/音频等技术标识
    tech_keywords = r'\b(1080p|2160p|720p|480p|BluRay|WEB-DL|HEVC|x265|x264|DTS|AAC|10bit|8bit|60fps|HDR|DV|REMUX|BDRip|WEBRip|HDTV)\b'
    
    # 截断技术参数部分
    parts = re.split(tech_keywords, base, flags=re.I)
    candidate = parts[0]  # 取技术参数之前的部分

    # 提取英文单词序列（允许数字年份）
    english_match = re.search(
        r'\b([A-Z][a-z]+(?:\.[A-Z][a-z]+){1,10})(?:\.(\d{4}))?\b',
        candidate
    )
    
    if english_match:
        title_part = english_match.group(1).replace('.', ' ').strip()
        year_part = english_match.group(2)
        
        # 过滤纯数字标题
        if title_part and not title_part.replace(' ', '').isdigit():
            return title_part, year_part
    
    return None, None


# 在 _step_tmdb_search() 或等效位置插入
def _step_tmdb_search_with_fallback(db, scraper, task, ai_result):
    """
    TMDB 四梯队搜索（含英文降级）

    梯队顺序：
    1. AI query + Year
    2. AI query（无 Year）
    3. 截断 query（去副标题）
    4. **英文降级：从原始文件名提取英文片名（新增）**
    """
    query = ai_result.get("query", "")
    year = ai_result.get("filename_year") or ai_result.get("knowledge_year", "")
    media_type = ai_result.get("type", "movie")

    # 第一梯队：AI query + Year
    results = scraper.search_media(query, media_type=media_type, year=year)
    if results:
        logger.info(f"[TMDB] 第一梯队命中: query='{query}', year={year}")
        return results[0]

    # 第二梯队：AI query（无 Year）
    results = scraper.search_media(query, media_type=media_type, year=None)
    if results:
        logger.info(f"[TMDB] 第二梯队命中: query='{query}', year=None")
        return results[0]

    # 第三梯队：截断 query（去副标题）
    if ":" in query or "：" in query:
        main_title = re.split(r'[:：]', query)[0].strip()
        results = scraper.search_media(main_title, media_type=media_type, year=None)
        if results:
            logger.info(f"[TMDB] 第三梯队命中: main_title='{main_title}'")
            return results[0]

    # **第四梯队（新增）：英文降级搜索**
    filename = task.get("file_name", "")
    english_title, extracted_year = _extract_english_title(filename)
    
    if english_title:
        logger.info(f"[TMDB] 第四梯队启动（英文降级）: english_title='{english_title}', extracted_year={extracted_year}")
        
        # 先用英文 + 年份搜索
        if extracted_year:
            results = scraper.search_media(english_title, media_type=media_type, year=extracted_year)
            if results:
                logger.info(f"[TMDB] 英文降级命中（含年份）: '{english_title}' ({extracted_year})")
                return results[0]
        
        # 再用纯英文搜索（无年份）
        results = scraper.search_media(english_title, media_type=media_type, year=None)
        if results:
            logger.info(f"[TMDB] 英文降级命中（无年份）: '{english_title}'")
            return results[0]

    # 四梯队全部失败
    logger.error(f"[TMDB] 四梯队搜索全部失败，标记任务为 failed")
    return None
```

---

### 第四阶段：AI 提示词优化（可选增强）

**目标文件**：`backend/app/infra/database/default_config.py`（推测）

**修改位置**：归档专家提示词（`expert_archive_rules`）

**当前提示词片段**（推测）：

```text
输出 JSON 字段：
- query: 用于 TMDB 搜索的片名（去除年份、技术参数）
- filename_year: 文件名中物理看到的年份
- confidence: 识别置信度（0.0-1.0）
```

**增强方案**：

```text
输出 JSON 字段：
- query: 用于 TMDB 搜索的片名（去除年份、技术参数、点号转空格）
- query_en: **（新增）英文片名（如果文件名包含英文单词，请提取并返回；否则留空）**
- filename_year: 文件名中物理看到的年份
- confidence: 识别置信度（0.0-1.0）

示例：
文件名: The.Lychee.Road.2025.2160p.60fps.HQ.WEB-DL.HEVC.10bit.DV.DTS5.1.4Audios-QHstudIo.mp4
输出:
{
  "query": "荔枝之路",
  "query_en": "The Lychee Road",  ← 新增字段
  "filename_year": "2025",
  "knowledge_year": "2025",
  "confidence": 0.95
}
```

**适配代码**：

在 `scrape_task.py` 的 TMDB 搜索链路中读取 `query_en` 字段作为第四梯队的输入。

```python
# 第四梯队：优先使用 AI 返回的英文片名
query_en = ai_result.get("query_en", "").strip()
if query_en:
    results = scraper.search_media(query_en, media_type=media_type, year=year)
    if results:
        logger.info(f"[TMDB] 第四梯队命中（AI 英文片名）: '{query_en}'")
        return results[0]

# 若 AI 未返回英文片名，则回退到正则提取
filename = task.get("file_name", "")
english_title, extracted_year = _extract_english_title(filename)
...
```

---

## 测试用例

### 用例 1：纯英文片名 + 低置信度

**输入**：`Silver.Medalist.2009.1080p.BluRay.DTS.x265-10bit-HDS.mkv`

**预期链路**：

1. AI 识别：`query="Silver Medalist"`, `confidence=0.3` → 被 Fail-Fast 拒绝 ✅
2. 不进入 TMDB 搜索（保持安全边界）

---

### 用例 2：中英混合片名 + 高置信度

**输入**：`The.Lychee.Road.2025.2160p.60fps.HQ.WEB-DL.HEVC.10bit.DV.DTS5.1.4Audios-QHstudIo.mp4`

**预期链路**：

1. AI 识别：`query="荔枝之路"`, `year="2025"`, `confidence=0.85` → 通过阈值 ✅
2. TMDB 第一梯队：`荔枝之路 + 2025` → 无结果
3. TMDB 第二梯队：`荔枝之路`（无年份）→ 无结果
4. TMDB 第四梯队（英文降级）：
   - 正则提取：`The Lychee Road + 2025` → **命中 TMDB** ✅
5. 任务状态：`scraped` / `archived`

---

### 用例 3：纯中文片名

**输入**：`庆余年.第二季.2024.4K.WEB-DL.H265.AAC-GPTHD.mkv`

**预期链路**：

1. AI 识别：`query="庆余年 第二季"`, `year="2024"`, `confidence=0.95` ✅
2. TMDB 第一梯队：`庆余年 第二季 + 2024` → **命中 TMDB** ✅
3. 不进入英文降级（中文片名已命中）

---

## 风险评估

### 风险点 1：英文片名误提取

**场景**：技术标签被误识别为片名（如 `BluRay.DTS.5.1` → `Bluray Dts`）

**缓解措施**：

- 正则过滤技术关键词（1080p / BluRay / HEVC 等）
- 要求英文片名至少包含 2 个单词
- 过滤纯大写或纯数字的候选

---

### 风险点 2：TMDB 多结果误匹配

**场景**：英文降级搜索返回多个候选，系统盲取第一个

**缓解措施**：

- 优先使用年份精确匹配（`year` 字段）
- 记录 `popularity` 排序（TMDB 已按热度排序）
- 日志中输出前 3 个候选供人工复查

---

### 风险点 3：置信度阈值放宽后误识别增加

**场景**：`confidence=0.7-0.8` 的识别结果中混入错误片名

**缓解措施**：

- 阈值设为 `0.7`（保守值，可后续根据数据调整）
- 对 `confidence < 0.8` 的任务在日志中标记 `[LOW_CONFIDENCE]`
- 前端任务列表可新增"待审核"状态（可选）

---

## 实施优先级

| 阶段 | 优先级 | 工作量 | 收益 | 建议动作 |
|------|--------|--------|------|----------|
| **第一阶段**：放宽置信度阈值 | 🔴 高 | 1 小时 | 立即解决 `confidence=0.85` 被拒问题 | **立即实施** |
| **第二阶段**：点号转空格归一化 | 🔴 高 | 2 小时 | 修复所有点分隔文件名搜索失败 | **立即实施** |
| **第三阶段**：英文降级搜索 | 🟡 中 | 4 小时 | 覆盖中文电影英文资源场景 | **本周实施** |
| **第四阶段**：AI 提示词优化 | 🟢 低 | 2 小时 | 减少正则兜底依赖，提升准确度 | 可选增强 |

---

## 成功指标

实施完成后，以下场景应全部通过：

1. ✅ `The.Lychee.Road.2025` 成功刮削到 TMDB 数据
2. ✅ `Silver.Medalist.2009` 若 AI 置信度 ≥ 0.7，则进入 TMDB 搜索
3. ✅ 纯中文片名（如 `庆余年`）不受影响，继续走第一梯队
4. ✅ 低置信度结果（`confidence < 0.7`）仍然被 Fail-Fast 拒绝
5. ✅ 日志中输出完整的四梯队搜索路径供人工复盘

---

## 后续优化方向

### 方向 1：AI 双语言识别能力增强

- 在提示词中要求 LLM 同时输出中文片名和英文片名（`query` / `query_en`）
- 减少对正则兜底的依赖

### 方向 2：TMDB 搜索结果排序优化

- 引入年份精确匹配权重（完全匹配 +10 分）
- 引入片名相似度算法（Levenshtein 距离）

### 方向 3：人工复审机制

- 对 `confidence < 0.8` 的任务标记为"待审核"
- 前端新增"批量确认"按钮，用户可快速审核批量识别结果

---

*计划编写时间：2026-06-11*  
*预计实施周期：第一、二阶段 1-2 天 | 第三阶段 3-5 天*  
*实施后跟踪：观察 1 周实际刮削成功率变化*
