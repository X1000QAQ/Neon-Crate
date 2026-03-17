# Neon Crate — 全自动影音库管理引擎

**版本**：v1.0.0  
**最后更新**：2026-03-17  
**状态**：正式发布  

> Neon Crate 是面向 NAS / 家庭媒体服务器场景的**全自动影音库管理引擎**。
> 一键扫描、AI 智能识别、TMDB 元数据刮削、自动归档、字幕下载——全流程自动化。

---

## 🚀 核心特性

- **AI 总控神经**：自然语言指令 → LLM 意图路由 → 自动触发扫描/刮削/下载/字幕任务
- **物理文件编排**：扫描下载目录 → 清洗文件名 → TMDB 刮削元数据 → SmartLink 硬链接归档
- **数据持久化**：SQLite WAL 模式，管理所有媒体任务状态、配置、归档记录
- **安全网关**：JWT 无状态鉴权 + Fernet 加密配置
- **AIO 静态服务**：生产模式单端口、单进程托管前后端

---

## 📚 文档导航

### 快速开始
- **[系统全景](./docs/01_架构设计/01_系统全景.md)** — 5分钟了解整体架构
- **[AIO 部署指南](./docs/04_运维部署/01_AIO部署指南.md)** — 从构建到部署

### 架构设计
- **[后端架构白皮书](./docs/01_架构设计/02_后端架构白皮书.md)** — 分层架构、数据库设计、API 路由
- **[前端架构白皮书](./docs/01_架构设计/03_前端架构白皮书.md)** — 组件设计、状态管理、性能优化
- **[全栈逻辑交互拓扑蓝图](./docs/01_架构设计/04_全栈逻辑交互拓扑蓝图.md)** — 3 张 Mermaid 架构图
- **[v1.0.0 核心逻辑蓝图（重绘）](./docs/01_架构设计/06_v1.0.0_核心逻辑蓝图重绘.md)** — 刮削终极流水线 / Singleflight 并发盾牌 / Neural Link 中枢
- **[刮削流水线数据生命周期](./docs/01_架构设计/05_刮削流水线数据生命周期.md)** — 全链路数据流白皮书（6字段证据模型 + YEAR_MIRROR 镜像校验）

### 数据契约
- **[标准数据契约](./docs/02_数据契约/01_标准数据契约.md)** — 前后端共享类型定义
- **[API 规范与鉴权](./docs/02_数据契约/02_API规范与鉴权.md)** — 接口规范、鉴权机制

### 核心功能
- **[AI 意图引擎](./docs/03_核心功能/01_AI意图引擎.md)** — LLM 意图识别、候选列表、下载触发
- **[全自动流水线](./docs/03_核心功能/02_全自动流水线.md)** — 扫描→刮削→归档→字幕完整链路
- **[元数据工厂](./docs/03_核心功能/03_元数据工厂.md)** — TMDB 搜索、NFO 生成、海报下载
- **[存储防御机制](./docs/03_核心功能/04_存储防御.md)** — 防重拦截、原子操作、安全防护

### 模块手册
- **[后端模块速查](./docs/05_模块手册/01_后端模块速查.md)** — 各模块方法速查
- **[前端模块速查](./docs/05_模块手册/02_前端模块速查.md)** — 组件职责与 Props 速查

### 完整索引
- **[文档索引](./docs/文档索引.md)** — 详细的文档结构与快速导航

---

## 🏗️ 技术栈

| 层次 | 技术 |
|------|------|
| 前端框架 | Next.js 14 (App Router) + TypeScript |
| 前端样式 | Tailwind CSS + 自定义 CSS 变量（霓虹主题）|
| 后端框架 | FastAPI 0.104.1 (Python 3.12) |
| 数据库 | SQLite（WAL 模式）|
| 加密 | cryptography（Fernet）+ PyJWT + passlib/bcrypt |
| AI 接入 | OpenAI 兼容 API（DeepSeek / Together / Ollama）|
| 外部 API | TMDB（元数据）/ OpenSubtitles（字幕）/ Radarr+Sonarr（下载）|
| 容器化 | Docker 多阶段构建（AIO 单容器）+ docker-compose |

---

## 📋 核心数据流

### 全量归档链路

```
POST /scan
  └─► ScanEngine（目录遍历 + 格式/大小过滤）
        └─► MediaCleaner（数据库驱动正则清洗）
              └─► db.insert_task()（path UNIQUE 防重入库）

POST /scrape_all
  └─► 获取防重锁（非阻塞，blocking=False）
        └─► 校验 TMDB API Key
              └─► 获取待刮削任务（双表联查：tasks + media_archive）
                    └─► 逐个处理任务
                          ├─► NFO 短路拦截（本地 NFO 存在）
                          ├─► AI 提炼逻辑（NFO 不存在）
                          ├─► TMDB 搜索与防重拦截
                          ├─► 就地补录（文件在 library 路径）
                          ├─► 归档全链路（文件在下载目录）
                          └─► 字幕白嫖（本地字幕检测）

POST /find_subtitles
  └─► SubtitleEngine
        ├─► 本地字幕检测（已有则跳过，零 API 消耗）
        └─► OpenSubtitles API → {视频名}.ai.zh-CN.srt
```

### AI 对话链路

```
AiSidebar.tsx
  └─► abortControllerRef.current.abort()  （掐断旧请求）
  └─► api.chat(message, signal)
        └─► POST /agent/chat
              └─► AIAgent.process_message()
                    ├─► LLMClient（意图识别，JSON 输出）
                    ├─► DOWNLOAD → ServarrClient（TMDB 侦察 + 精准下载）
                    └─► ACTION_SCAN/SCRAPE/SUBTITLE → 触发对应后台任务
```

---

## 🔐 核心架构约束（红线）

| # | 约束 | 违反后果 |
|---|------|----------|
| 1 | 所有过滤正则必须来自数据库，严禁硬编码 | 正则规则与 RegexLab 脱钩，用户设置失效 |
| 2 | 所有 AI 规则必须来自数据库 | AI 行为无法通过 WebUI 热更新 |
| 3 | 前端所有 HTTP 调用只能经过 `lib/api.ts` | 401 处理、超时熔断失效 |
| 4 | 敏感 API Key 必须通过 `CryptoManager` 加密存储 | 配置文件明文泄露密钥 |
| 5 | `mark_task_as_ignored_and_inherit` 不可拆分 | 前端 VHS 特效失效，ignored 任务白板显示 |
| 6 | `is_archive` 必须在所有跨端通信中传递 | 后端无法确定操作哪张表 |
| 7 | 前端所有 UI 文本通过 `t(key)` 获取 | i18n 切换失效，中英文混显 |
| 8 | 冷表写回必须以 `original_task_id` 为查询键，热表以 `id` | `update_archive_sub_status` 命中 0 行，字幕状态卡死在 pending |

完整约束清单见 [文档索引](./docs/文档索引.md)。

---

## 🎯 快速导航

### 我是新成员
1. 阅读 [系统全景](./docs/01_架构设计/01_系统全景.md)
2. 选择后端或前端，阅读对应的架构白皮书
3. 查看 [模块手册](./docs/05_模块手册/) 了解具体实现

### 我要开发新功能
1. 查看 [标准数据契约](./docs/02_数据契约/01_标准数据契约.md) 了解类型定义
2. 查看 [API 规范](./docs/02_数据契约/02_API规范与鉴权.md) 了解接口设计
3. 查看 [模块手册](./docs/05_模块手册/) 了解现有实现

### 我要部署系统
1. 阅读 [AIO 部署指南](./docs/04_运维部署/01_AIO部署指南.md)
2. 按照指南构建 Docker 镜像
3. 使用 docker-compose 启动

### 我要理解某个功能
- [AI 意图引擎](./docs/03_核心功能/01_AI意图引擎.md)
- [全自动流水线](./docs/03_核心功能/02_全自动流水线.md)
- [元数据工厂](./docs/03_核心功能/03_元数据工厂.md)
- [存储防御机制](./docs/03_核心功能/04_存储防御.md)

---

## 📊 项目统计

| 指标 | 数值 |
|------|------|
| 源码文件 | 11 个 |
| 关键函数 | 14 个 |
| 源码注释行数 | 470+ |
| 关键分支节点 | 30+ |
| 文档文件 | 12 个 |
| 文档新增行数 | 1280+ |
| Mermaid 架构图 | 3 张 |

---

## 🚀 快速开始

### 本地开发

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

# 前端（新终端）
cd frontend
npm install
npm run dev
```

访问 `http://localhost:3000`

### Docker 部署

```bash
# 构建镜像
docker build -t neon-crate:latest .

# 启动容器
docker-compose up -d
```

访问 `http://localhost:8000`

---

## 📝 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v1.0.0 | 2026-03-17 | [Armored 架构加固] 除垢行动 Phase 1-3：前端装甲化（渲染风暴熔断、SPA 尊严修复、i18n 全覆盖）|
| v1.0.0 | 2026-03-17 | [Armored 状态机对齐] 全链路状态机协议对齐：次元 ID 隔离修复、异步字幕智能轮询、i18n 字典重编 |
| v1.0.0 | 2026-03-17 | [Enhanced 注释升维] 全栈源码级注释补全 + 文库重编与升维 |
| v1.0.0 | 2026-03-17 | [Stable 初始构建] 全自动影音库管理引擎初始版本 |

---

## 📄 许可证

MIT License

---

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

*Neon Crate | 全自动影音库管理引擎 | v1.0.0 | 2026-03-17*
