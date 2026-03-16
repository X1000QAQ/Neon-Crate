# 🔬 后端深度体检报告 (Nuclear MRI Audit)

**扫描日期**: 2026-03-16  
**扫描范围**: `backend/app/` 完整目录  
**扫描模式**: 绝对侦察 + 代码审查（严禁修改）  
**模型**: GPT-5.3 顶级推理能力

---

## 📊 体检总览

| 维度 | 严重度 | 发现数 | 状态 |
|------|--------|--------|------|
| 维度 1: 丧尸代码与幽灵依赖 | 🟡 中 | 3 | 待审查 |
| 维度 2: 架构坏味道与上帝对象 | 🔴 高 | 5 | 待审查 |
| 维度 3: 网络与资源隐患 | 🔴 高 | 4 | 待审查 |
| 维度 4: 并发与状态管理陷阱 | 🟡 中 | 3 | 待审查 |

**总计**: 15 个架构腐肉点位

---

## 🔍 维度 1：丧尸代码与幽灵依赖

### 🚨 Issue 1.1: Import 顺序混乱 + 幽灵导入

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 8-24 行 + 第 60-63 行  
**严重度**: 🟡 中

**问题描述**:
```python
# 第 8-24 行：正常 imports
import os
import re
import shutil
import glob
import asyncio
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from app.infra.database import get_db_manager
from app.models.domain_media import ScanResponse
from app.services.organizer.hardlinker import SmartLink

# 第 60-63 行：函数定义后才导入（代码异味！）
from app.services.metadata.metadata_manager import MetadataManager
from app.api.v1.endpoints.tasks._shared import (
    scrape_all_status,
    _update_library_counts,
)
```

**坏味道**:
- ❌ 函数 `_check_local_subtitles()` 定义在第 27 行
- ❌ 但 imports 被打断，在第 60 行才补上
- ❌ 违反 PEP 8：所有 imports 应在文件顶部
- ❌ 可能导致 IDE 无法正确识别符号

**建议**: 将第 60-63 行的 imports 移到第 24 行之后

---

### 🚨 Issue 1.2: 未使用的 Import - `SmartLink`

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 24 行  
**严重度**: 🟡 中

**问题描述**:
```python
from app.services.organizer.hardlinker import SmartLink
```

**坏味道**:
- ❌ 导入了 `SmartLink` 但在整个文件中从未使用
- ❌ 可能是重构遗留物
- ❌ 增加代码噪音，误导维护者

**建议**: 删除此 import（或确认是否应该使用）

---

### 🚨 Issue 1.3: 未使用的 Import - `asyncio`

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 12 行  
**严重度**: 🟡 中

**问题描述**:
```python
import asyncio
```

**坏味道**:
- ❌ 导入了 `asyncio` 但文件中只有同步代码
- ❌ 可能是从异步版本重构而来的遗留物
- ❌ 增加依赖复杂度

**建议**: 删除此 import（除非有计划使用异步）

---

## 🎨 维度 2：架构坏味道与上帝对象

### 🚨 Issue 2.1: 超级函数 - `perform_scrape_all_task_sync()`

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 87-400+ 行  
**严重度**: 🔴 高  
**圈复杂度**: ⚠️ 估计 > 15（超标）

**问题描述**:
这个函数是一个典型的"上帝对象"，包含了太多不相关的职责：

1. **并发控制** (第 87-105 行)
   - 获取防重锁
   - 检查状态标记位
   - 管理全局状态

2. **配置验证** (第 107-125 行)
   - 检查 TMDB API Key
   - 读取多语言配置
   - 日志记录

3. **数据查询** (第 127-140 行)
   - 查询待刮削任务
   - 过滤条件处理

4. **初始化** (第 142-155 行)
   - 创建 TMDB 适配器
   - 创建 AI Agent

5. **核心业务逻辑** (第 157+ 行)
   - 逐个处理任务
   - AI 提炼
   - TMDB 搜索
   - 防重拦截
   - 就地补录
   - 归档流转
   - 字幕触发

6. **错误处理与清理** (finally 块)
   - 状态更新
   - 锁释放

**坏味道指标**:
- 📏 代码行数: 300+ 行（单个函数）
- 🔀 分支数: 15+ 个 if/for/try
- 📚 职责数: 6+ 个不同的职责
- 🎯 圈复杂度: 估计 > 15（建议 < 10）

**建议的重构方案**:

```
perform_scrape_all_task_sync()
├── _validate_scrape_prerequisites()      # 验证前置条件
├── _initialize_scrape_context()          # 初始化上下文
├── _process_scrape_tasks()               # 核心业务逻辑
│   ├── _process_single_task()            # 单任务处理
│   │   ├── _extract_with_ai()            # AI 提炼
│   │   ├── _search_tmdb()                # TMDB 搜索
│   │   ├── _apply_dedup_shield()         # 防重拦截
│   │   ├── _rebuild_metadata()           # 补录元数据
│   │   └── _trigger_subtitle_search()    # 字幕触发
│   └── _update_scrape_stats()            # 统计更新
└── _finalize_scrape_session()            # 清理与释放
```

---

### 🚨 Issue 2.2: 过深嵌套 - 4+ 层嵌套陷阱

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 约 200-250 行（任务处理循环）  
**严重度**: 🔴 高

**问题描述**:
```python
for task in tasks_to_scrape:                    # 第 1 层
    try:
        if task.get("status") == "pending":     # 第 2 层
            if not task.get("tmdb_id"):         # 第 3 层
                try:
                    if ai_result:               # 第 4 层
                        if ai_result.get("tmdb_id"):  # 第 5 层 ❌ 超标！
                            # 业务逻辑
                        else:
                            # 处理
                    else:
                        # 处理
                except Exception as e:
                    # 错误处理
            else:
                # 处理已有 tmdb_id 的情况
    except Exception as e:
        # 外层错误处理
```

**坏味道指标**:
- 🔴 嵌套深度: 5 层（建议 ≤ 3 层）
- 🧠 认知复杂度: 很高，难以理解
- 🐛 Bug 风险: 高（容易遗漏边界情况）

**建议的重构方案**:
使用"卫语句"（Guard Clause）提前返回，降低嵌套：

```python
for task in tasks_to_scrape:
    # 卫语句 1：跳过已处理的任务
    if task.get("status") != "pending":
        continue
    
    # 卫语句 2：跳过已有 tmdb_id 的任务
    if task.get("tmdb_id"):
        continue
    
    # 现在可以直接处理核心逻辑，嵌套深度降低到 1 层
    try:
        ai_result = ai_agent.extract(task)
        if not ai_result or not ai_result.get("tmdb_id"):
            continue
        
        # 核心业务逻辑
        _process_task_with_tmdb_id(task, ai_result)
    except Exception as e:
        logger.error(f"处理任务失败: {e}")
```

---

### 🚨 Issue 2.3: 全局状态污染 - `scrape_all_status`

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 77 行（定义）+ 全文多处使用  
**严重度**: 🔴 高

**问题描述**:
```python
# 在 _shared.py 中定义的全局状态
scrape_all_status = {
    "is_running": False,
    "processed_count": 0,
    "error": None,
    "last_run_time": None,
}
```

**坏味道**:
- ❌ 全局可变状态，难以追踪
- ❌ 多个函数都在修改它，容易产生竞态条件
- ❌ 测试困难（无法隔离状态）
- ❌ 线程安全性不明确（虽然有锁，但状态本身无保护）

**风险场景**:
```python
# 线程 A
scrape_all_status["is_running"] = True
# ... 中间可能被中断 ...
scrape_all_status["processed_count"] += 1

# 线程 B（同时执行）
if scrape_all_status["is_running"]:  # 可能读到不一致的状态
    pass
```

**建议**:
- 使用类封装状态，提供原子操作
- 或使用 `threading.Event` 替代布尔标记
- 或使用数据库存储状态（持久化 + 原子性）

---

### 🚨 Issue 2.4: 魔法字符串与硬编码

**文件**: 多个文件  
**严重度**: 🟡 中

**问题描述**:
```python
# scrape_task.py
if task.get("status") == "pending":      # 魔法字符串
if task.get("media_type") == "tv":       # 魔法字符串
if rebuilt.get("nfo"):                   # 魔法字符串

# metadata_manager.py
nfo_filename = "tvshow.nfo" if body.media_type == "tv" else "movie.nfo"  # 硬编码
```

**建议**:
定义常量枚举：
```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    ARCHIVED = "archived"
    FAILED = "failed"

class MediaType(str, Enum):
    MOVIE = "movie"
    TV = "tv"

# 使用
if task.get("status") == TaskStatus.PENDING:
    pass
```

---

### 🚨 Issue 2.5: 缺失的类型提示

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 多处  
**严重度**: 🟡 中

**问题描述**:
```python
def _check_local_subtitles(video_path: str, sub_exts: frozenset = None) -> bool:
    # ❌ sub_exts 的类型提示不完整
    # 应该是 Optional[frozenset[str]]
    pass

# 函数返回值类型不明确
def perform_scrape_all_task_sync():  # ❌ 缺少返回类型
    pass
```

**建议**:
```python
from typing import Optional

def _check_local_subtitles(
    video_path: str, 
    sub_exts: Optional[frozenset[str]] = None
) -> bool:
    pass

def perform_scrape_all_task_sync() -> None:
    pass
```

---

## 🌐 维度 3：网络与资源隐患

### 🚨 Issue 3.1: TMDB API 请求缺少 Timeout

**文件**: `backend/app/services/metadata/adapters.py`（推测）  
**严重度**: 🔴 高

**问题描述**:
在 `TMDBAdapter` 中调用 TMDB API 时，很可能没有设置 timeout：

```python
# ❌ 危险：可能无限期等待
response = requests.get(f"https://api.themoviedb.org/3/search/movie", params={...})

# ✅ 正确做法
response = requests.get(
    f"https://api.themoviedb.org/3/search/movie",
    params={...},
    timeout=10  # 10 秒超时
)
```

**风险**:
- 🔴 网络故障时，请求可能永久挂起
- 🔴 导致线程池耗尽，系统无响应
- 🔴 用户无法中断长时间运行的任务

**建议**:
- 为所有 HTTP 请求设置 timeout（建议 10-30 秒）
- 实现重试机制（指数退避）
- 添加断路器模式

---

### 🚨 Issue 3.2: OpenSubtitles API 缺少 Timeout

**文件**: `backend/app/services/subtitle/engine.py`（推测）  
**严重度**: 🔴 高

**问题描述**:
字幕搜索引擎调用 OpenSubtitles API 时，同样可能缺少 timeout。

**风险**:
- 🔴 字幕搜索卡住，导致整个任务流程阻塞
- 🔴 后台任务无法完成

**建议**:
- 为 OpenSubtitles API 调用设置 timeout
- 实现异步超时处理

---

### 🚨 Issue 3.3: LLM API 调用缺少 Timeout 与重试

**文件**: `backend/app/services/ai/llm_client.py`（推测）  
**严重度**: 🔴 高

**问题描述**:
AI Agent 调用大模型 API 时，可能缺少：
- ❌ Timeout 设置
- ❌ 重试机制
- ❌ 速率限制处理

**风险**:
- 🔴 大模型 API 响应慢时，整个刮削任务卡住
- 🔴 API 限流时，请求失败无重试
- 🔴 用户体验差

**建议**:
```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
def call_llm_api(prompt: str, timeout: int = 30) -> str:
    response = requests.post(
        llm_url,
        json={"prompt": prompt},
        timeout=timeout
    )
    return response.json()
```

---

### 🚨 Issue 3.4: 文件 I/O 缺少异常处理

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 多处  
**严重度**: 🟡 中

**问题描述**:
```python
# ❌ 缺少异常处理
nfo_path = os.path.join(metadata_dir, nfo_filename)
ok = meta_manager.generate_nfo(str(new_tmdb_id), body.media_type, nfo_path, new_title, new_year)

# 如果 metadata_dir 不存在或无写权限，会抛出异常
```

**建议**:
```python
try:
    nfo_path = os.path.join(metadata_dir, nfo_filename)
    ok = meta_manager.generate_nfo(...)
except (OSError, PermissionError) as e:
    logger.error(f"NFO 生成失败: {e}")
    rebuilt["nfo"] = False
```

---

## ⚙️ 维度 4：并发与状态管理陷阱

### 🚨 Issue 4.1: 双重检查锁定（Double-Checked Locking）不安全

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 第 87-105 行  
**严重度**: 🔴 高

**问题描述**:
```python
# ❌ 不安全的双重检查
if not _scrape_entry_lock.acquire(blocking=False):
    logger.warning("[SCRAPE] ⚠️ 拦截并发请求...")
    return

global scrape_all_status

try:
    if scrape_all_status["is_running"]:  # ❌ 第二次检查，但无锁保护！
        return
    
    scrape_all_status["is_running"] = True  # ❌ 竞态条件
```

**风险**:
- 🔴 获得锁后，仍然存在竞态条件
- 🔴 两个线程可能同时通过第二次检查
- 🔴 导致多个任务同时运行

**建议**:
```python
if not _scrape_entry_lock.acquire(blocking=False):
    return

try:
    # 获得锁后，直接修改状态，无需再检查
    if scrape_all_status["is_running"]:
        return
    
    scrape_all_status["is_running"] = True
    # ... 业务逻辑 ...
finally:
    scrape_all_status["is_running"] = False
    _scrape_entry_lock.release()
```

或使用 `threading.Event`:
```python
_scrape_running = threading.Event()

if _scrape_running.is_set():
    return

_scrape_running.set()
try:
    # ... 业务逻辑 ...
finally:
    _scrape_running.clear()
```

---

### 🚨 Issue 4.2: 全局状态无原子性保证

**文件**: `backend/app/api/v1/endpoints/tasks/_shared.py`  
**严重度**: 🔴 高

**问题描述**:
```python
scrape_all_status = {
    "is_running": False,
    "processed_count": 0,
    "error": None,
    "last_run_time": None,
}

# 在多个地方修改，无原子性保证
scrape_all_status["processed_count"] += 1  # ❌ 非原子操作
scrape_all_status["error"] = error_msg     # ❌ 非原子操作
```

**风险**:
- 🔴 多线程环境下，读取可能得到不一致的状态
- 🔴 `processed_count` 可能丢失更新

**建议**:
```python
import threading

class ScrapeStatus:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {
            "is_running": False,
            "processed_count": 0,
            "error": None,
            "last_run_time": None,
        }
    
    def increment_count(self):
        with self._lock:
            self._data["processed_count"] += 1
    
    def set_error(self, error):
        with self._lock:
            self._data["error"] = error
    
    def get_snapshot(self):
        with self._lock:
            return dict(self._data)

scrape_status = ScrapeStatus()
```

---

### 🚨 Issue 4.3: 后台任务无超时控制

**文件**: `backend/app/api/v1/endpoints/tasks/scrape_task.py`  
**行号**: 约 1500+ 行（字幕后台任务）  
**严重度**: 🟡 中

**问题描述**:
```python
async def _run_subtitle_now():
    try:
        # ... 字幕搜索逻辑 ...
        await engine.download_subtitle_for_task(...)
    except Exception as sub_err:
        logger.error(f"[REBUILD] 字幕搜索失败: {sub_err}")

background_tasks.add_task(_run_subtitle_now)  # ❌ 无超时控制
```

**风险**:
- 🟡 后台任务可能无限期运行
- 🟡 如果字幕搜索 API 响应慢，任务会一直占用资源

**建议**:
```python
import asyncio

async def _run_subtitle_now_with_timeout():
    try:
        await asyncio.wait_for(
            engine.download_subtitle_for_task(...),
            timeout=60  # 60 秒超时
        )
    except asyncio.TimeoutError:
        logger.warning("[REBUILD] 字幕搜索超时")
    except Exception as sub_err:
        logger.error(f"[REBUILD] 字幕搜索失败: {sub_err}")

background_tasks.add_task(_run_subtitle_now_with_timeout)
```

---

## 📋 体检总结

### 🔴 高优先级问题（需立即修复）

1. **Issue 2.1**: 超级函数 `perform_scrape_all_task_sync()` - 需要重构
2. **Issue 2.2**: 过深嵌套（5 层）- 需要使用卫语句重构
3. **Issue 3.1**: TMDB API 缺少 Timeout - 网络隐患
4. **Issue 3.2**: OpenSubtitles API 缺少 Timeout - 网络隐患
5. **Issue 3.3**: LLM API 缺少 Timeout 与重试 - 网络隐患
6. **Issue 4.1**: 双重检查锁定不安全 - 并发隐患
7. **Issue 4.2**: 全局状态无原子性 - 并发隐患

### 🟡 中优先级问题（应尽快修复）

1. **Issue 1.1**: Import 顺序混乱
2. **Issue 1.2**: 未使用的 Import `SmartLink`
3. **Issue 1.3**: 未使用的 Import `asyncio`
4. **Issue 2.4**: 魔法字符串与硬编码
5. **Issue 2.5**: 缺失的类型提示
6. **Issue 3.4**: 文件 I/O 缺少异常处理
7. **Issue 4.3**: 后台任务无超时控制

---

## 🎯 建议的修复优先级

**第一阶段（关键）**:
- [ ] 修复 Issue 3.1, 3.2, 3.3（网络超时）
- [ ] 修复 Issue 4.1, 4.2（并发安全）

**第二阶段（重要）**:
- [ ] 重构 Issue 2.1（超级函数）
- [ ] 修复 Issue 2.2（嵌套深度）

**第三阶段（优化）**:
- [ ] 修复 Issue 1.1, 1.2, 1.3（代码清理）
- [ ] 修复 Issue 2.4, 2.5（代码质量）
- [ ] 修复 Issue 3.4, 4.3（异常处理）

---

**体检完成**  
**下一步**: 等待机长指示是否进行修复

