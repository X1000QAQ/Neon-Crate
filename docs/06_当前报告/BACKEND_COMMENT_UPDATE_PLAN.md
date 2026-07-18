# 后端代码中文注释计划方案

**生成时间**：2026-06-11  
**目标目录**：`backend/`  
**方案文件**：`docs/06_当前报告/BACKEND_COMMENT_UPDATE_PLAN.md`  
**执行方式**：先计划、后分批操作；每批修改前先读代码，避免注释与实际逻辑不一致。

---

## 1. 本次目标

为后端 Python 代码补齐规范、准确、可维护的中文技术注释，重点覆盖：

1. 文件级模块说明：每个核心 `.py` 文件顶部说明职责、边界、调用场景。
2. 类与函数说明：核心服务、仓储、路由、模型补充参数、返回值、异常和业务链路。
3. 关键业务边界说明：扫描、刮削、AI 意图识别、归档、字幕、配置、鉴权、下载联动。
4. 删除功能残留核查：重点确认已删除的“物理正则功能”是否还有配置、接口、字段或误导性注释残留。
5. 风险控制：只添加或修正注释，不改业务逻辑、导出符号、API 路由、数据结构和默认配置。

---

## 2. 已完成的前置检查

### 2.1 后端目录结构概览

后端主体位于 `backend/app/`，当前结构如下：

```text
backend/app/
├── api/                    # FastAPI 路由层
│   ├── auth.py             # 登录、初始化、Token 鉴权
│   └── v1/
│       ├── api.py          # v1 路由聚合
│       ├── deps.py         # 依赖注入
│       └── endpoints/
│           ├── agent.py    # AI 对话入口
│           ├── system.py   # 系统状态与日志接口
│           └── tasks/      # 媒体任务相关接口
├── core/                   # 应用工厂与生命周期
├── infra/                  # 基础设施层
│   ├── config/             # 配置路径与环境变量
│   ├── database/           # 数据库管理与仓储
│   ├── security/           # 加密与安全工具
│   ├── constants.py        # 扩展名等常量
│   └── http_utils.py       # HTTP 工具
├── models/                 # Pydantic 领域模型
├── services/               # 业务服务层
│   ├── ai/                 # AI Agent、意图分发、LLM 客户端
│   ├── downloader/         # Radarr / Sonarr 下载联动
│   ├── metadata/           # TMDB / NFO / 元数据校验
│   ├── organizer/          # 硬链接 / 软链接归档
│   ├── rebuilder/          # NFO / 海报 / 字幕重构
│   ├── scraper/            # 扫描、过滤、结构化清洗、刮削引擎
│   ├── subtitle/           # 字幕补完
│   └── system/             # 系统监控
├── cli.py                  # CLI 入口
└── main.py                 # ASGI 入口
```

### 2.2 物理正则残留检查结论

已检索并抽查以下关键词：

```text
物理正则 / 路径正则 / 规则正则
physical_regex / physical.*regex / regex.*physical
path_regex / regex_rules / physical_rules / pattern_rules
rename_regex / organize_regex / clean_regex / match_regex
regex / regexp / re.compile / re.sub / pattern
```

结论：

1. **未发现明确的“物理正则功能”入口残留**：没有找到 `physical_regex`、`path_regex`、`regex_rules` 等配置项、接口或字段。
2. **存在废弃字段兼容清理逻辑**：`backend/app/infra/database/repositories/config_repo.py` 中保留：
   - `DEPRECATED_CONFIG_KEYS = frozenset({"filename_clean_regex"})`
   - 读取、写入、保存、创世自愈阶段都会忽略或剥离该字段。
   - 这属于“删除后的兼容清理逻辑”，不是功能残留，建议保留，并在注释中明确说明。
3. **存在正常业务正则**：`scraper/cleaner.py`、`scraper/engine.py` 等文件仍使用 `re.compile` / `re.search`，用途是：
   - 视频扩展名识别
   - 年份提取
   - 季集坐标提取
   - 样片目录/样片文件过滤
   - 归档路径安全化
   这些属于确定性结构化处理，不等同于已删除的“物理正则功能”。
4. **需要修正或强化的说明点**：
   - `scraper/cleaner.py` 顶部已明确写明“语义清洗由 AI Agent 负责，不再使用 RegexLab / DB 正则”。后续补注释时应保留这条边界。
   - `config_repo.py` 的 `DEPRECATED_CONFIG_KEYS` 应补充中文说明：这是对旧配置字段的幂等剥离，不代表功能仍可用。
   - 不应新增任何“正则配置中心”“物理正则规则”“用户自定义正则”等误导性描述。

---

## 3. 注释总原则

### 3.1 中文技术文档规范

- 中英文之间加空格，例如：`FastAPI 路由`、`AI Agent`、`TMDB API`。
- 中文与数字之间加空格，例如：`50 MB`、`4 个阶段`。
- 中文语境使用全角标点。
- 代码、字段、函数、路径使用反引号，例如：`perform_scan_task_sync()`、`filename_clean_regex`。
- 避免机翻腔，优先使用自然中文短句。

### 3.2 注释内容边界

注释应该解释：

- 为什么这样设计。
- 这个模块在链路中处于哪一层。
- 输入、输出、异常、状态流转。
- 哪些逻辑不能改，改了会影响哪些链路。
- 已废弃功能为什么还保留兼容清理逻辑。

注释不应该：

- 复述显而易见的代码。
- 写“导入模块”“定义变量”这类无信息量注释。
- 把已删除功能描述成仍然存在。
- 编造代码中不存在的能力。

### 3.3 对“物理正则”的专项约束

后续注释时统一采用以下口径：

```text
旧的“物理正则 / DB 正则清洗”能力已删除。
当前后端只保留两类逻辑：
1. AI 语义识别：由 AI Agent 根据提示词解析片名、类型、季集和年份。
2. 确定性结构化处理：用固定代码提取扩展名、年份、季集坐标、样片过滤和路径安全化。
```

如遇到 `filename_clean_regex`，注释应写为：

```text
废弃配置字段：仅用于启动和读写时剥离旧配置，防止历史 config.json 污染当前语义链路。
不要恢复为用户可配置功能。
```

---

## 4. 分批执行计划

## 第 1 批：启动、应用工厂、基础设施入口

### 范围

```text
backend/app/main.py
backend/app/cli.py
backend/app/core/app_factory.py
backend/app/core/lifespan.py
backend/app/infra/config/__init__.py
backend/app/infra/constants.py
backend/app/infra/http_utils.py
backend/app/infra/security/crypto.py
```

### 注释重点

- `main.py`：ASGI 入口，说明 `app_factory` 如何创建 FastAPI 应用。
- `app_factory.py`：说明中间件、路由、静态资源、CORS、异常处理的装配顺序。
- `lifespan.py`：说明启动初始化、定时任务、资源释放边界。
- `config/__init__.py`：说明环境变量、数据目录、路径计算。
- `constants.py`：说明视频/字幕扩展名常量与配置项的关系。
- `crypto.py`：说明敏感密钥加密目的，不暴露实现细节。

### 风险

低。主要是文件头和函数注释，不改逻辑。

---

## 第 2 批：数据库管理与仓储层

### 范围

```text
backend/app/infra/database/db_manager.py
backend/app/infra/database/default_config.py
backend/app/infra/database/repositories/base.py
backend/app/infra/database/repositories/config_repo.py
backend/app/infra/database/repositories/task_repo.py
backend/app/infra/database/repositories/archive_repo.py
backend/app/infra/database/repositories/path_repo.py
backend/app/infra/database/repositories/stats_repo.py
```

### 注释重点

- `db_manager.py`：说明数据库初始化、仓储聚合、对外统一入口。
- `default_config.py`：说明 Code as Config、AI 默认提示词、格式默认值。
- `config_repo.py`：重点说明：
  - `config.json` 与 `secure_keys.json` 分离。
  - 敏感键自动加解密。
  - `@prompts/` 引用机制。
  - `DEPRECATED_CONFIG_KEYS` 是废弃字段剥离，不是功能入口。
  - `filename_clean_regex` 只用于历史配置清理。
- `task_repo.py`：说明热表任务状态、重复检测、任务更新。
- `archive_repo.py`：说明冷热表归档与历史数据查询。
- `stats_repo.py`：说明统计缓存与仪表盘展示关系。

### 物理正则专项检查

重点检查并注释：

```text
DEPRECATED_CONFIG_KEYS = frozenset({"filename_clean_regex"})
```

正确注释方向：

```text
这是旧版配置字段的清理名单，用于防止历史配置继续污染当前 AI 语义识别链路。
```

禁止写成：

```text
这里配置文件名清洗正则。
```

### 风险

中。仓储层被多条链路调用。只允许补注释，不改接口和字段。

---

## 第 3 批：Pydantic 领域模型

### 范围

```text
backend/app/models/domain_media.py
backend/app/models/domain_system.py
```

### 注释重点

- `Task`：说明 `media_type`、`status`、`is_archive` 的前后端契约。
- `SystemSettings`：说明配置分类、敏感字段、LLM 双引擎、AI 提示词字段。
- `PathConfig`：说明 `download` / `library` 路径类型，以及 `movie` / `tv` / `mixed` 分类。
- `PendingActionPayload`：说明 AI 下载授权弹窗的数据来源。
- `ChatRequest` / `ChatResponse`：说明 AI 对话返回意图契约。

### 物理正则专项检查

确认 `SystemSettings` 中没有 `filename_clean_regex` 或其他正则配置字段。若后续发现，必须标记为残留，先询问是否删除或迁移，而不是直接注释为有效功能。

### 风险

低到中。模型字段是前后端契约，注释必须准确。

---

## 第 4 批：API 路由层

### 范围

```text
backend/app/api/auth.py
backend/app/api/v1/api.py
backend/app/api/v1/deps.py
backend/app/api/v1/endpoints/agent.py
backend/app/api/v1/endpoints/system.py
backend/app/api/v1/endpoints/tasks/_shared.py
backend/app/api/v1/endpoints/tasks/router.py
backend/app/api/v1/endpoints/tasks/media_router.py
backend/app/api/v1/endpoints/tasks/settings_router.py
backend/app/api/v1/endpoints/tasks/scan_task.py
backend/app/api/v1/endpoints/tasks/scrape_task.py
backend/app/api/v1/endpoints/tasks/subtitle_task.py
backend/app/api/v1/endpoints/tasks/rebuild_task.py
```

### 注释重点

- `auth.py`：初始化、登录、JWT 颁发和校验。
- `deps.py`：数据库依赖、用户鉴权依赖。
- `agent.py`：AI 聊天入口、意图分发、下载确认链路。
- `system.py`：系统状态、日志和监控信息。
- `settings_router.py`：配置读取、保存、重置、API Key 校验。
- `scan_task.py`：物理扫描任务、并发锁、路径白名单、inode 防重。
- `scrape_task.py`：全量刮削任务调度。
- `subtitle_task.py`：字幕任务调度。
- `rebuild_task.py`：NFO / 海报 / 字幕重构。

### 物理正则专项检查

- `scan_task.py` 中“物理扫描”“物理 inode”“物理检查路径”是磁盘层含义，不是“物理正则”。注释要避免混淆。
- `settings_router.py` 不应出现正则配置接口描述。

### 风险

中。路由层注释会直接影响 API 文档理解，必须与当前路由行为一致。

---

## 第 5 批：扫描与刮削链路

### 范围

```text
backend/app/services/scraper/filters.py
backend/app/services/scraper/cleaner.py
backend/app/services/scraper/engine.py
```

### 注释重点

- `filters.py`：说明 50 MB 体积过滤、样片目录/文件名过滤、扩展名过滤。
- `cleaner.py`：重点说明当前职责边界：
  - 不再承载 DB 正则清洗。
  - 只做确定性结构化提取。
  - 语义清洗交给 AI Agent。
- `engine.py`：说明并发扫描、路径去重、inode 防重、同级文件上下文采集。

### 物理正则专项检查

这是最容易误解的一批。需要明确：

1. `re.compile` 的存在不代表“物理正则功能”仍存在。
2. `_YEAR_PATTERN`、`_SEASON_EPISODE_PATTERNS` 是固定代码契约，用于结构化坐标提取。
3. 不再支持用户通过配置修改文件名清洗正则。
4. `ScanEngine` 入库时不解析片名，只采集上下文给后续 AI 链路。

### 风险

中。此处是“已删除物理正则功能”的关键解释点。

---

## 第 6 批：AI 服务链路

### 范围

```text
backend/app/services/ai/agent.py
backend/app/services/ai/dispatcher.py
backend/app/services/ai/llm_client.py
```

### 注释重点

- `agent.py`：说明 AI 对话入口、提示词加载、JSON 输出解析、下载授权前置。
- `dispatcher.py`：说明意图白名单、任务路由、本地搜索/系统状态/下载候选处理。
- `llm_client.py`：说明云端和本地 LLM 的请求封装、超时、错误处理。

### 与物理正则的关系

AI 服务是当前语义清洗和意图识别的核心。注释应说明：

```text
文件名中的语义噪声清洗由 AI 提示词完成，而不是由用户配置正则完成。
```

### 风险

中到高。AI 链路复杂，注释前必须逐函数阅读，避免误导。

---

## 第 7 批：元数据、NFO 与重构链路

### 范围

```text
backend/app/services/metadata/adapters.py
backend/app/services/metadata/metadata_manager.py
backend/app/services/metadata/nfo_parser.py
backend/app/services/metadata/validator.py
backend/app/services/rebuilder/engines.py
backend/app/services/rebuilder/rebuild_utils.py
```

### 注释重点

- TMDB 搜索、电影/剧集详情获取、海报路径处理。
- 元数据校验和候选匹配。
- NFO 解析与生成。
- 重构任务如何复用元数据和归档路径。

### 风险

中。需要区分“重新生成元数据文件”和“重新归档文件”的边界。

---

## 第 8 批：归档、下载、字幕、系统监控

### 范围

```text
backend/app/services/organizer/hardlinker.py
backend/app/services/downloader/servarr.py
backend/app/services/subtitle/engine.py
backend/app/services/system/monitor.py
```

### 注释重点

- `hardlinker.py`：说明硬链接优先、跨分区软链接兜底、字幕同步、防交叉污染。
- `servarr.py`：说明 Radarr / Sonarr 下载任务创建、质量配置、根路径选择。
- `subtitle/engine.py`：说明字幕搜索、下载、语言后缀、状态更新。
- `monitor.py`：说明系统日志、CPU / 内存 / 磁盘信息采集。

### 风险

中。涉及文件系统和第三方服务，注释应强调副作用和失败兜底。

---

## 第 9 批：包初始化与脚本

### 范围

```text
backend/app/**/__init__.py
backend/refresh_config.py
backend/force_refresh_config.py
```

### 注释重点

- `__init__.py`：只补必要模块说明，避免过度注释空文件。
- 刷新脚本：说明用途、执行场景、是否会改写配置文件。

### 风险

低。

---

## 5. 建议执行顺序

推荐按以下顺序逐步操作：

```text
1. 第 2 批：数据库与配置仓储层
   原因：先把废弃正则字段和配置契约讲清楚。

2. 第 5 批：扫描与刮削链路
   原因：这里最容易和“物理正则”混淆，需要优先修正注释口径。

3. 第 3 批：领域模型
   原因：确认前后端字段契约，避免后续 API 注释混乱。

4. 第 4 批：API 路由层
   原因：对外接口文档依赖模型和配置语义。

5. 第 6 批：AI 服务链路
   原因：语义清洗与意图识别是当前替代旧正则功能的核心。

6. 第 7 批：元数据与重构链路

7. 第 8 批：归档、下载、字幕、监控

8. 第 1 批：启动与基础设施入口
   原因：相对稳定，可在核心业务注释确定后统一补齐。

9. 第 9 批：包初始化与脚本
```

---

## 6. 每批操作流程

每一批执行时遵循以下流程：

```text
1. 读取文件内容。
2. 检查是否已经有文件头注释。
3. 检查是否出现已删除的物理正则相关字段或误导性描述。
4. 如涉及函数 / 类 / 方法，先做影响分析。
5. 添加或修正中文注释。
6. 运行 linter / 诊断检查。
7. 更新本报告或新增批次完成记录。
```

---

## 7. 注释模板

### 7.1 文件头模板

```python
"""
模块名 - 简短职责

职责：
- 说明这个模块负责什么。
- 说明它处于哪条业务链路。
- 说明它不负责什么，尤其是容易误解的边界。

关键边界：
- 不修改业务数据 / 不直接调用外部服务 / 不承担语义清洗等。

维护提示：
- 修改本模块时需要同步检查哪些调用方或配置项。
"""
```

### 7.2 函数注释模板

```python
def function_name(...):
    """
    一句话说明函数目的。

    业务链路：
    描述输入从哪里来，输出给谁使用。

    Args:
        xxx: 参数含义。

    Returns:
        返回值结构和业务含义。

    Raises:
        可能抛出的异常或失败条件。
    """
```

### 7.3 废弃字段注释模板

```python
# 废弃字段清理名单：用于剥离历史 config.json 中残留的旧版文件名正则配置。
# 当前系统不再支持用户配置“物理正则清洗”，语义识别由 AI Agent 完成。
# 保留此名单是为了幂等清理旧配置，不代表该功能仍然可用。
DEPRECATED_CONFIG_KEYS = frozenset({"filename_clean_regex"})
```

---

## 8. 当前已识别的重点文件与注意事项

| 文件 | 当前观察 | 注释处理建议 |
|------|----------|--------------|
| `config_repo.py` | 有 `DEPRECATED_CONFIG_KEYS = {"filename_clean_regex"}` | 明确说明是历史字段剥离，不是功能入口 |
| `cleaner.py` | 已说明不再使用 RegexLab / DB 正则 | 保留该口径，补充固定结构化提取说明 |
| `engine.py` | 扫描只采集上下文，`clean_name/year/season/episode` 保留空兼容字段 | 注释强调解析由 AI 刮削链路负责 |
| `scan_task.py` | 大量“物理 inode / 物理扫描”注释 | 保持“物理”指磁盘层，不要误写为正则功能 |
| `domain_system.py` | `SystemSettings` 无正则清洗字段 | 说明当前配置项不包含用户正则清洗能力 |
| `settings_router.py` | 配置保存和重置接口无正则配置入口 | 注释中不要出现“正则配置” |
| `default_config.py` | AI 提示词中有“物理看到的年份”表述 | 这是自然语言提示词，不是物理正则功能 |

---

## 9. 验收标准

完成后应满足：

1. 后端核心 `.py` 文件均有准确的文件级中文说明。
2. 核心类 / 函数有参数、返回值、业务链路和异常说明。
3. 所有新增注释符合中文技术文档规范。
4. 没有把已删除的“物理正则功能”描述成仍可配置或可使用。
5. `filename_clean_regex` 只作为历史废弃字段清理逻辑出现。
6. 正常业务正则（扩展名、年份、季集、样片过滤）被正确解释为固定结构化处理。
7. 修改后不引入 linter 错误。

---

## 10. 执行进度记录

### 第 1 批：启动、应用工厂、基础设施入口

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/main.py
backend/app/cli.py
backend/app/core/app_factory.py
backend/app/core/lifespan.py
backend/app/infra/config/__init__.py
backend/app/infra/constants.py
backend/app/infra/http_utils.py
backend/app/infra/security/crypto.py
```

**完成内容**：

1. `main.py`：补强 ASGI 入口说明，明确 `create_app()` 与 `lifespan` 的装配关系。
2. `cli.py`：补强离线管理入口说明，明确只处理管理员账号文件，不触碰媒体任务和配置仓储。
3. `app_factory.py`：补强 FastAPI 装配顺序说明，强调 CORS、路由、异常处理、健康检查、文档路由和静态资源挂载顺序。
4. `lifespan.py`：补强启动、巡逻、关闭资源边界说明，明确自动巡逻只编排任务，不直接实现业务细节。
5. `config/__init__.py`：补强环境变量、`.env`、默认值优先级，以及 Docker / data 路径约定。
6. `constants.py`：补强视频和字幕扩展名分层说明，以及与数据库格式配置的兜底关系。
7. `http_utils.py`：补强共享 HTTP 客户端、连接池、指数退避和高风险调用面的说明。
8. `crypto.py`：补强敏感密钥加密、密码哈希、JWT 会话和 `data/secret.key` 持久化边界说明。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `create_app` | LOW | 1 个直接影响，无执行流程影响 |
| `lifespan` | LOW | 无直接影响 |
| `cron_scanner_loop` | LOW | 1 个直接影响，影响生命周期流程 |
| `CryptoManager` | LOW | 10 个间接影响，主要是鉴权和密钥能力 |
| `Settings` | LOW | 4 个直接影响 |
| `get_settings` | LOW | 5 个影响 |
| `cli` | LOW | 2 个直接影响 |
| `http_get_with_retry` | CRITICAL | 13 个直接调用，影响元数据、下载、重构和 API Key 验证流程 |

**CRITICAL 风险处理说明**：

`http_get_with_retry()` 是外部服务请求共享底座，影响面较大。本批严格只修改模块注释，不改函数签名、返回值、超时、重试条件、连接池或异常处理逻辑。

**复查结果**：

```text
第 1 批 8 个文件首行均为模块 docstring。
ReadLints：8 个文件均无 linter errors。
```

---

### 第 2 批：数据库与配置仓储层

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/infra/database/db_manager.py
backend/app/infra/database/default_config.py
backend/app/infra/database/repositories/base.py
backend/app/infra/database/repositories/config_repo.py
backend/app/infra/database/repositories/task_repo.py
backend/app/infra/database/repositories/archive_repo.py
backend/app/infra/database/repositories/path_repo.py
backend/app/infra/database/repositories/stats_repo.py
```

**完成内容**：

1. `db_manager.py`：补强 SQLite 连接池、Schema 初始化、仓储门面、热表 / 冷表边界和敏感密钥迁移说明。
2. `default_config.py`：补强 Code as Config、AI 默认提示词、格式扩展名默认值，以及“物理看到的年份”不是物理正则功能的说明。
3. `base.py`：补强 Repository 共享依赖、连接函数、锁和 `_like()` 转义工具说明。
4. `config_repo.py`：重点补强配置仓储、敏感密钥分离、提示词文件化、创世自愈和废弃字段清理说明。
5. `task_repo.py`：补强任务热表、状态流转、冷热表流转触发、`ignored` 视觉契约和任务生命周期说明。
6. `archive_repo.py`：补强冷表归档、`original_task_id` 对外 ID 契约、归档事务原子性和媒体库路径约束说明。
7. `path_repo.py`：补强下载目录 / 媒体库路径配置、`config.json.paths` 数据边界和路径可用性检查边界说明。
8. `stats_repo.py`：补强仪表盘和媒体墙只读查询、热表 / 冷表联合视图、`include_ignored` 和剧集季集级重复检测说明。

**物理正则残留处理结果**：

已在 `config_repo.py` 中明确统一口径：

```text
filename_clean_regex 是旧版配置字段，仅作为历史配置清理名单存在。
当前系统不再支持用户配置“物理正则清洗”。
语义识别由 AI Agent 和提示词完成。
DEPRECATED_CONFIG_KEYS 只负责读写时忽略、启动时剥离旧字段，不代表该功能仍然可用。
```

本批没有新增任何“正则配置中心”“物理正则规则”“用户自定义正则”等误导性描述。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `DatabaseManager` | LOW | 16 个影响，1 个直接影响 |
| `get_db_manager` | LOW | 无直接影响 |
| `ConfigRepo` | LOW | 6 个影响，2 个直接影响 |
| `TaskRepo` | LOW | 3 个影响，1 个直接影响 |
| `ArchiveRepo` | LOW | 3 个影响，1 个直接影响 |
| `update_task_status` | LOW | 图谱未显示直接影响，但实际为任务状态门面背后关键方法 |
| `get_tasks_needing_scrape` | LOW | 图谱未显示直接影响，但实际为刮削任务查询入口 |
| `archive_task` | LOW | 图谱未显示直接影响，但实际由归档状态流转触发 |
| `get_all_data` | LOW | 图谱未显示直接影响，但实际为媒体墙 / AI 状态读取入口 |
| `get_managed_paths` | LOW | 图谱未显示直接影响，但实际为扫描和归档路径链路入口 |

**复查结果**：

```text
第 2 批 8 个文件首行均为模块 docstring。
filename_clean_regex 仅出现在废弃字段清理说明与清理逻辑中。
ReadLints：8 个文件均无 linter errors。
```

---

### 第 3 批：Pydantic 领域模型中文注释

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/models/domain_media.py
backend/app/models/domain_system.py
backend/app/models/__init__.py
```

**完成内容**：

1. `domain_media.py`：补强媒体任务、扫描响应和仪表盘统计的 API 契约说明。
2. `domain_media.py`：明确 `Task.media_type` 对外屏蔽数据库 `type` 字段差异，说明冷热表 `is_archive` 寻址语义。
3. `domain_media.py`：说明 `year` 兼容 `int | str` 的原因，以及模型层不承担文件名重新解析或物理正则清洗职责。
4. `domain_system.py`：补强配置、鉴权、批量操作、AI 对话、授权确认载荷和候选项模型说明。
5. `domain_system.py`：明确 `SystemSettings` 不包含 `filename_clean_regex`，当前系统不再提供用户自定义文件名物理正则清洗能力。
6. `domain_system.py`：补强 `PendingActionPayload` 的“等待用户确认”语义，避免把下载确认载荷误读为任务已执行。
7. `domain_system.py`：补强 `ChatResponse.candidates` 的候选决策说明，强调系列或模糊片名应由用户选择。
8. `models/__init__.py`：补强模型包入口说明，明确按领域模块显式导入，避免隐式依赖。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `Task` | LOW | 10 个影响，4 个直接影响 |
| `StatsResponse` | LOW | 10 个影响，4 个直接影响 |
| `ScanResponse` | LOW | 10 个影响，4 个直接影响 |
| `PathConfig` | LOW | 8 个影响，4 个直接影响 |
| `SystemSettings` | LOW | 8 个影响，4 个直接影响 |
| `SettingsConfig` | LOW | 8 个影响，4 个直接影响 |
| `PendingActionPayload` | LOW | 8 个影响，4 个直接影响 |
| `ChatRequest` | LOW | 8 个影响，4 个直接影响 |
| `ChatResponse` | LOW | 8 个影响，4 个直接影响 |
| `CandidateItem` | LOW | 8 个影响，4 个直接影响 |

**物理正则口径检查**：

```text
模型层仅说明“不包含 filename_clean_regex / 不承担物理正则清洗职责”。
未新增任何可配置正则、正则配置中心或用户自定义物理正则能力描述。
```

**复查结果**：

```text
第 3 批 3 个文件首行均为模块 docstring。
ReadLints：3 个文件均无 linter errors。
```

---

### 第 4 批：API 路由层中文注释

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/api/__init__.py
backend/app/api/auth.py
backend/app/api/v1/__init__.py
backend/app/api/v1/api.py
backend/app/api/v1/deps.py
backend/app/api/v1/endpoints/__init__.py
backend/app/api/v1/endpoints/system.py
backend/app/api/v1/endpoints/agent.py
backend/app/api/v1/endpoints/tasks/__init__.py
backend/app/api/v1/endpoints/tasks/router.py
backend/app/api/v1/endpoints/tasks/_shared.py
backend/app/api/v1/endpoints/tasks/media_router.py
backend/app/api/v1/endpoints/tasks/settings_router.py
backend/app/api/v1/endpoints/tasks/scan_task.py
backend/app/api/v1/endpoints/tasks/scrape_task.py
backend/app/api/v1/endpoints/tasks/subtitle_task.py
backend/app/api/v1/endpoints/tasks/rebuild_task.py
```

**完成内容**：

1. `api.py`：补强 v1 路由聚合器、前缀分组和破坏性路径变更提示。
2. `auth.py`：补强初始化、登录、Token 校验、全局守卫和 401 / 403 语义边界说明。
3. `deps.py`：补强 FastAPI 依赖注入容器、`DbDep` 类型别名和测试替换边界说明。
4. `system.py`：补强统计、日志、图片代理、路径白名单、敏感目录黑名单、后缀校验和 TTL 缓存说明。
5. `agent.py`：补强 AI 对话、意图白名单、口令即执行、频率管控、下载确认载荷和授权执行说明。
6. `tasks/router.py`：补强任务路由聚合策略，说明 `GET ""` 不能随意替换为 `GET "/"`。
7. `tasks/_shared.py`：补强进程内任务状态、媒体库计数缓存和固定扩展名白名单边界说明。
8. `media_router.py`：补强任务列表 DTO 适配、热表 / 冷表合并、`type -> media_type`、`path -> file_path` 和安全删除说明。
9. `settings_router.py`：补强配置读取、保存、API Key 验证、分区重置、媒体库路径约束和废弃正则入口边界说明。
10. `scan_task.py`：补强物理扫描、路径权威、`mixed` 隔离、inode 防重、后台线程和锁释放说明。
11. `scrape_task.py`：补强刮削链路、AI 语义提炼、路径类型权威、年份证据校验和并发锁说明；同步修正旧注释中“AI 失败降级正则清洗”的错误口径。
12. `subtitle_task.py`：补强字幕补完、本地字幕短路、OpenSubtitles 频率保护、后台线程和并发锁说明。
13. `rebuild_task.py`：补强手动补录、资产修复、TMDB 候选搜索、TV 根目录白名单安全锁和物理正则废弃边界说明。
14. API 包入口文件：补强包职责、导出边界和隐式副作用说明。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `get_current_user` | LOW | 无直接影响 |
| `get_all_tasks` | LOW | 无直接影响 |
| `chat` | LOW | 无直接影响 |
| `perform_scan_task_sync` | LOW | 无直接影响 |
| `perform_scrape_all_task_sync` | LOW | 无直接影响 |
| `update_settings` | LOW | 无直接影响 |
| `perform_find_subtitles_task_sync` | LOW | 无直接影响 |
| `manual_rebuild` | LOW | 无直接影响 |
| `proxy_image` | LOW | 无直接影响 |
| `api_router` | LOW | 无直接影响 |

**物理正则口径检查**：

```text
API 路由层只保留“不恢复 / 不提供用户自定义文件名物理正则清洗能力”的边界说明。
已修正 scrape_task.py 中旧注释“AI 失败则降级使用正则清洗名”的错误口径。
未新增任何正则配置中心、filename_clean_regex 入口或用户自定义清洗能力描述。
```

**复查结果**：

```text
第 4 批 17 个 API 文件首行均为模块 docstring。
ReadLints：17 个文件均无 linter errors。
计划文件无 linter errors。
```

---

### 第 5 批：AI、刮削、元数据服务层中文注释

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/services/ai/__init__.py
backend/app/services/ai/agent.py
backend/app/services/ai/llm_client.py
backend/app/services/ai/dispatcher.py
backend/app/services/scraper/__init__.py
backend/app/services/scraper/cleaner.py
backend/app/services/scraper/engine.py
backend/app/services/scraper/filters.py
backend/app/services/metadata/__init__.py
backend/app/services/metadata/adapters.py
backend/app/services/metadata/metadata_manager.py
backend/app/services/metadata/nfo_parser.py
backend/app/services/metadata/validator.py
```

**完成内容**：

1. `ai/agent.py`：补强 AI Agent 对话编排、意图识别、授权决策、候选状态持久化和下载不直连执行边界说明。
2. `ai/agent.py`：修正 `ai_identify_media()` 旧注释中“正则清洗保底”的错误口径，改为强 Schema + 调用方 Fail-Fast。
3. `ai/llm_client.py`：补强云端 / 本地双引擎调度、`force_json`、超时、重试、429 退避和降级返回语义说明。
4. `ai/dispatcher.py`：补强 `AIActionEnum` 白名单、`AIIntentModel` 强校验、`Dispatcher` 冷却只读预检和执行后写入时间戳边界说明。
5. `scraper/cleaner.py`：补强结构化文件名工具边界，强调正则只用于固定格式提取和路径安全处理，不替代 AI 做语义清洗。
6. `scraper/engine.py`：补强并发扫描、视频扩展名过滤、路径 / inode 防重、同级文件上下文采集、软链接防循环和深度限制说明。
7. `scraper/filters.py`：补强物理体积过滤器说明，明确其不做扩展名判断、不解析片名、不访问 TMDB。
8. `metadata/adapters.py`：补强 TMDB 搜索、详情、外部 ID、语言参数、精确端点优先和 `/search/multi` 降级策略说明。
9. `metadata/metadata_manager.py`：补强 NFO 生成、海报 / Fanart / 季海报下载、路径防穿越、资产复用和空详情对象说明。
10. `metadata/nfo_parser.py`：补强 NFO 本地真理解析器、自动刮削轨 / 手动核武轨隔离、三层 XML 容错和正则兜底边界说明。
11. `metadata/validator.py`：补强 TMDB 单集坐标校验防火墙、返回语义、建议坐标和只读校验边界说明。
12. AI、刮削、元数据包入口文件：补强导出职责和避免隐式副作用说明。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `AIAgent` | LOW | direct=2，受影响符号 6 个 |
| `LLMClient` | LOW | direct=2，受影响符号 6 个 |
| `Dispatcher` | LOW | direct=2，受影响符号 6 个 |
| `ScanEngine` | LOW | direct=1，受影响符号 6 个 |
| `MediaCleaner` | LOW | direct=3，受影响符号 9 个 |
| `TMDBAdapter` | MEDIUM | direct=6，受影响符号 13 个 |
| `MetadataManager` | LOW | direct=2，受影响符号 6 个 |
| `_validate_path` | CRITICAL | direct=5，影响元数据写盘和刮削归档链路；本批只改注释，未改控制流 |
| `parse_nfo` | HIGH | direct=4，影响扫描、刮削和重构相关流程；本批只改注释，未改解析逻辑 |
| `validate_tmdb_metadata` | LOW | direct=1，影响刮削任务单集校验流程 |

**物理正则口径检查**：

```text
服务层只保留“正则用于固定结构提取、XML 字段兜底或路径安全处理”的说明。
已修正 AIAgent.ai_identify_media() 中“解析失败时使用正则清洗名保底”的旧口径。
未新增 filename_clean_regex、RegexLab、DB 正则或用户自定义文件名物理正则清洗入口。
```

**复查结果**：

```text
第 5 批 13 个服务文件首行均为模块 docstring。
ReadLints：13 个服务文件均无 linter errors。
计划文件无 linter errors。
```

---

### 第 6 批：下载器、字幕、重构和系统服务层中文注释

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/services/downloader/__init__.py
backend/app/services/downloader/servarr.py
backend/app/services/subtitle/__init__.py
backend/app/services/subtitle/engine.py
backend/app/services/rebuilder/__init__.py
backend/app/services/rebuilder/engines.py
backend/app/services/rebuilder/rebuild_utils.py
backend/app/services/system/__init__.py
backend/app/services/system/monitor.py
```

**完成内容**：

1. `downloader/servarr.py`：补强 Radarr / Sonarr 下载任务分发、TMDB 预侦察、`tmdb:{id}` 精准 lookup、查重审计和幂等返回说明。
2. `downloader/servarr.py`：明确下载意图必须经过 AI 候选确认和 `/confirm` 授权端点，不能直接由模型输出触发。
3. `subtitle/engine.py`：补强 OpenSubtitles 搜索、听障字幕过滤、简体优先评分、规范化落盘、热表 / 冷表状态回写和目标路径优先说明。
4. `subtitle/engine.py`：补强 429 / 5xx 指数退避、401 / 403 / 配额耗尽熔断、无 ID 时 query 兜底等外部 API 边界。
5. `rebuilder/engines.py`：补强 `BaseRebuildEngine`、`NuclearEngine`、`AssetPatchEngine` 三类执行器的职责、Patch / Nuclear 双轨语义和安全约束。
6. `rebuilder/engines.py`：明确核级重构涉及移动文件、删除旧 NFO、清理目录和批量回写双表，是高风险全量重构轨道。
7. `rebuilder/engines.py`：明确资产补丁轨道的 `path_changed`、`is_subtitle_only` 防误杀策略，以及 TV 单集不覆盖既有 `tvshow.nfo` 的金标边界。
8. `rebuilder/rebuild_utils.py`：补强本地字幕探测、核级清理保险栓、同剧 / 同季记录查询、TV 目标路径计算、视频定位和物理兄弟集扫描说明。
9. `rebuilder/rebuild_utils.py`：强调 `metadata_dir` 必须位于 `library_root` 内、`library_root` 过浅拒绝操作、删除前二次解析路径防软链穿越。
10. `system/monitor.py`：补强磁盘、CPU、Radarr / Sonarr 心跳、30 秒 TTL 缓存和 AI 状态汇报真实数据来源说明。
11. `system/monitor.py`：明确未配置返回 `NOT_CONFIGURED`、心跳异常返回 `OFFLINE`、磁盘异常返回 `UNKNOWN`，避免向上抛出网络异常。
12. 下载器、字幕、重构、系统包入口文件：补强导出职责、授权调用边界和避免导入副作用说明。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `ServarrClient` | LOW | direct=1，受影响符号 5 个 |
| `SubtitleEngine` | LOW | direct=2，受影响符号 9 个 |
| `SubtitleFatalError` | LOW | direct=2，受影响符号 9 个 |
| `BaseRebuildEngine` | LOW | direct=3，影响 Rebuilder 模块 |
| `NuclearEngine` | LOW | direct=1，受影响符号 3 个 |
| `AssetPatchEngine` | LOW | direct=1，受影响符号 3 个 |
| `_nuclear_clean_directory` | LOW | direct=1，影响重构 execute 流程 |
| `_locate_video_for_task` | LOW | direct=2，影响重构 execute 流程 |
| `MonitorService` | LOW | direct=1，受影响符号 4 个 |

**安全边界口径检查**：

```text
下载器：明确下载必须经授权确认链路调用，ServarrClient 不直接接收模型输出。
字幕：明确 OpenSubtitles 熔断、退避、配额耗尽和目标路径落盘边界。
重构：明确 library_root / metadata_dir 安全边界、核级删除保险栓和防软链穿越。
系统：明确监控服务只读，不写数据库，异常降级为状态值返回。
未新增 filename_clean_regex、RegexLab、DB 正则或用户自定义文件名物理正则清洗入口。
```

**复查结果**：

```text
第 6 批 9 个服务文件首行均为模块 docstring。
ReadLints：9 个服务文件均无 linter errors。
计划文件无 linter errors。
```

---

### 第 7 批：基础设施层、配置仓储、数据库和启动生命周期中文注释

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/infra/__init__.py
backend/app/infra/config/__init__.py
backend/app/infra/http_utils.py
backend/app/infra/security/__init__.py
backend/app/infra/security/crypto.py
backend/app/infra/database/__init__.py
backend/app/infra/database/db_manager.py
backend/app/infra/database/repositories/__init__.py
backend/app/infra/database/repositories/config_repo.py
backend/app/infra/database/repositories/path_repo.py
backend/app/infra/database/repositories/stats_repo.py
backend/app/infra/database/repositories/archive_repo.py
backend/app/infra/database/repositories/task_repo.py
backend/app/core/__init__.py
backend/app/core/app_factory.py
backend/app/core/lifespan.py
```

**完成内容**：

1. `db_manager.py`：补强 SQLite 数据库管理器、线程级连接池、Schema 初始化、版本迁移、敏感密钥迁移和 Repository 外观兼容边界说明。
2. `db_manager.py`：补强 `get_db_manager()` 双重检查锁单例说明，明确首次访问才创建数据库门面。
3. `config_repo.py`：补强配置仓储对 `config.json`、`secure_keys.json`、`data/prompts/*.txt` 三类介质的协调职责说明。
4. `config_repo.py`：继续明确 `filename_clean_regex` 只作为废弃字段清理名单存在，不恢复用户自定义物理正则清洗能力。
5. `task_repo.py`：补强热表任务生命周期、扫描入库、刮削 / 字幕状态、忽略、失败、归档和删除职责说明。
6. `archive_repo.py`：补强冷表归档仓储、`original_task_id` 前端 ID 契约、冷热表原子流转和媒体库路径约束说明。
7. `stats_repo.py`：补强仪表盘、媒体墙、同源海报继承和 IMDb + 季集重复检测只读边界说明。
8. `path_repo.py`：补强下载目录、电影媒体库、剧集媒体库路径配置边界说明，明确仓储只保存配置，不判断路径可用性。
9. `crypto.py`：补强 Fernet API Key 加密、Bcrypt 密码哈希、JWT 签发验证、`data/secret.key` 根密钥持久化边界说明。
10. `http_utils.py`：补强 `http_get_with_retry()` 作为 TMDB、海报 / Fanart、API Key 验证和重构搜索共享底座的 CRITICAL 影响提示。
11. `app_factory.py`：补强 FastAPI 应用装配顺序、中间件、路由、异常处理、文档路由和静态资源挂载顺序说明。
12. `lifespan.py`：补强队列化日志、环境检查、数据库初始化、孤儿任务重置、自动巡逻后台任务、关闭取消和日志 flush 边界说明。
13. `infra`、`database`、`repositories`、`security`、`core` 包入口：补强导出职责和避免隐式业务副作用说明。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `DatabaseManager` | LOW | direct=1，受影响符号 16 个 |
| `ConfigRepo` | LOW | direct=2，受影响符号 6 个 |
| `TaskRepo` | LOW | direct=1，受影响符号 3 个 |
| `ArchiveRepo` | LOW | direct=1，受影响符号 3 个 |
| `CryptoManager` | LOW | direct=1，受影响符号 10 个 |
| `http_get_with_retry` | CRITICAL | direct=13，影响 9 条执行流程，覆盖 Metadata、Downloader、Tasks 模块；本批只改注释，未改网络行为 |
| `create_app` | LOW | direct=1，应用装配入口 |
| `lifespan` | LOW | direct=0，FastAPI 生命周期管理器 |
| `cron_scanner_loop` | LOW | direct=1，影响生命周期巡逻流程 |
| `Settings` | LOW | direct=4，环境配置入口 |

**安全与生命周期口径检查**：

```text
配置仓储：filename_clean_regex 只被幂等剥离，不恢复物理正则清洗能力。
安全模块：secret.key 是历史 API Key 密文和 JWT 的根密钥，必须随 data/ 持久化。
HTTP 底座：http_get_with_retry 是 CRITICAL 共享底座，本批只补注释，不改超时、重试或返回值。
数据库：冷热表 ID 契约、原子归档、线程级连接池和迁移边界已补充。
生命周期：启动初始化、自动巡逻任务、关闭取消和日志队列停止边界已补充。
未新增 filename_clean_regex、RegexLab、DB 正则或用户自定义文件名物理正则清洗入口。
```

**复查结果**：

```text
第 7 批 19 个基础设施 / 核心文件首行均为模块 docstring。
ReadLints：19 个文件均无 linter errors。
python3 -m py_compile：19 个文件编译通过。
计划文件无 linter errors。
```

---

### 第 8 批：后端注释体系最终复核、遗留英文注释清理和总体验证

**状态**：已完成  
**完成时间**：2026-06-11  
**修改范围**：

```text
backend/app/services/organizer/__init__.py
backend/app/services/organizer/hardlinker.py
backend/app/api/v1/endpoints/tasks/scan_task.py
backend/app/api/v1/endpoints/tasks/subtitle_task.py
backend/app/api/v1/endpoints/tasks/scrape_task.py
backend/app/services/metadata/nfo_parser.py
backend/app/services/metadata/metadata_manager.py
backend/app/infra/database/db_manager.py
backend/app/infra/database/repositories/task_repo.py
```

**完成内容**：

1. 全局扫描 `backend/app/**/*.py`，确认 67 个 Python 文件的模块级 docstring 覆盖情况。
2. 为 `services/organizer/__init__.py` 补充模块级中文 docstring，消除最后一个缺失文件。
3. 补强 `services/organizer/hardlinker.py` 的模块职责、调用边界和 `SmartLink` 类说明。
4. 将 `SmartLink` 静态调用说明中的英文 `WARNING` 和命令示例改为中文表述，避免注释中继续保留英文警戒标记。
5. 清理扫描、字幕、刮削、NFO 解析和元数据路径校验中的 `DO NOT MODIFY` 英文警戒标记，统一为“禁止随意修改 / 架构警告”。
6. 清理 `TaskRepo.update_any_task_metadata()` 中 `ARCHITECT WARNING` 和 `DB` 英文缩写口径，统一为中文说明。
7. 保留并复核所有物理正则禁用说明，确认其均为“禁用 / 废弃 / 不恢复”的防回归口径。
8. 对全后端执行模块 docstring 覆盖检查、英文警戒标记检查、物理正则口径检查、linter 检查和 Python 编译检查。

**影响分析摘要**：

| 符号 | 风险 | 摘要 |
|------|------|------|
| `SmartLink` | LOW | direct=2，受影响符号 7 个；本批只改注释 |
| `perform_scan_task_sync` | LOW | direct=0；本批只改锁边界注释 |
| `perform_find_subtitles_task_sync` | LOW | direct=0；本批只改锁边界注释 |
| `parse_nfo` | HIGH | direct=4，影响自动刮削、扫描和重构流程；本批只改注释，不改解析逻辑 |
| `update_any_task_metadata` | LOW | direct=0；本批只改注释 |
| `_validate_path` | CRITICAL | direct=5，影响元数据写盘和刮削归档链路；本批只改注释，不改路径校验逻辑 |

**最终复核结果**：

```text
后端 Python 文件总数：67
模块级 docstring 缺失：0
英文警戒标记 DO NOT / WARNING: / TODO / FIXME：0
物理正则相关说明：23 处，均为禁用、废弃、剥离或不恢复口径
ReadLints：本批编辑的 9 个文件均无 linter errors
python3 -m py_compile backend/app/**/*.py：67 个文件编译通过
计划文件无 linter errors
```

**物理正则口径最终结论**：

```text
系统不恢复 filename_clean_regex。
系统不恢复 RegexLab / DB 正则清洗链路。
系统不提供用户自定义文件名物理正则清洗入口。
允许保留的正则仅限固定结构提取、XML 字段兜底、路径安全处理、扩展名 / 季集号识别等确定性工具用途。
媒体文件名语义识别继续由 LLM 强 Schema、TMDB 校验和刮削 Fail-Fast 链路承担。
```

---

## 11. 下一步建议

后端中文注释体系 8 批已完成。若继续推进，建议进入：

```text
前端注释体系复核，或准备提交前的 GitNexus detect_changes 与端到端回归验证
```

原因：后端路由、模型、服务、基础设施和生命周期注释已完成主要覆盖，并通过全局编译与本批 linter 检查。提交前建议再做一次 GitNexus 变更检测和关键后端测试 / 启动验证。

---

*最后更新：2026-06-11 | 第 8 批后端中文注释最终复核已完成*
