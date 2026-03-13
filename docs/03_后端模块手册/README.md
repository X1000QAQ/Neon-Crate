# 后端模块手册

> **版本**: 2.1.0 — 基于 2026-03-12 全量重构后的真实代码  
> **架构模式**: 应用工厂 + 依赖注入 + 任务包拆分  
> **整体评分**: 9.25/10

---

## 目录结构

```
03_后端模块手册/
├── README.md                  ← 本文件：总目录导航
├── main.md                    ← 应用入口（极简 12 行）
│
├── 01_core/                   ← 应用核心（工厂 + 生命周期）
│   ├── app_factory.md         ← FastAPI 应用工厂
│   └── lifespan.md            ← 生命周期 + 自动巡逻流水线
│
├── 02_infra/                  ← 基础设施层
│   ├── config.md              ← 环境变量配置（pydantic-settings）
│   ├── database.md            ← SQLite 数据库管理器（WAL + 原子写入）
│   ├── security.md            ← 神盾计划（Fernet + Bcrypt + JWT）
│   └── http_utils.md          ← 公共 HTTP 工具（指数退避重试）
│
├── 03_api/                    ← API 路由层
│   ├── auth.md                ← 鉴权路由（/api/v1/auth/*）
│   ├── deps.md                ← 依赖注入容器（DbDep）
│   ├── agent.md               ← AI 对话端点（/api/v1/agent/chat）
│   ├── system.md              ← 系统端点（stats / logs / image-proxy）
│   └── tasks/                 ← 任务包（已拆分为 5 个子模块）
│       ├── overview.md        ← tasks 包总览 + 路由聚合
│       ├── scan.md            ← 物理扫描任务
│       ├── scrape.md          ← 全量刮削任务
│       ├── subtitle.md        ← 字幕补完任务
│       ├── media.md           ← 媒体库 CRUD 路由
│       └── settings.md        ← 系统配置路由
│
├── 04_services/               ← 业务服务层
│   ├── scraper.md             ← 扫描引擎（engine + cleaner + filters）
│   ├── metadata.md            ← TMDB 元数据（adapters + metadata_manager）
│   ├── ai.md                  ← AI 服务层（agent + llm_client）
│   ├── organizer.md           ← 智能链接归档（SmartLink）
│   ├── subtitle.md            ← 字幕引擎（SubtitleEngine）
│   └── downloader.md          ← Servarr 下载器（Radarr/Sonarr）
│
└── 05_models/                 ← 领域模型层
    ├── domain_media.md        ← 媒体领域模型（Task / StatsResponse 等）
    └── domain_system.md       ← 系统领域模型（Settings / Auth / Chat 等）
```

---

## 架构分层总览

```
┌─────────────────────────────────────────────────────┐
│                    main.py (12行)                    │
│              create_app() + lifespan()               │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│               01_core / app_factory                  │
│  中间件 → 路由注册 → 异常处理器 → 静态资源挂载        │
└──────────┬───────────────────────────────┬──────────┘
           │                               │
┌──────────▼──────────┐       ┌────────────▼──────────┐
│      03_api/         │       │      01_core/lifespan  │
│  auth / agent /      │       │  日志初始化 + DB初始化  │
│  system / tasks/     │       │  + cron_scanner_loop   │
└──────────┬──────────┘       └────────────────────────┘
           │ Depends(get_db_manager)
┌──────────▼──────────────────────────────────────────┐
│                   04_services/                       │
│  scraper │ metadata │ ai │ organizer │ subtitle │ dl  │
└──────────┬──────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────┐
│                   02_infra/                          │
│       database │ security │ config │ http_utils       │
└─────────────────────────────────────────────────────┘
```

---

## 请求生命周期（完整流水线）

```
HTTP Request
  → JWT 鉴权中间件（app_factory 全局 Depends）
  → 路由匹配（api_router / auth_router / public_router）
  → FastAPI 依赖注入（DbDep = Depends(get_db_manager)）
  → 端点函数执行
  → BackgroundTasks（scan / scrape / subtitle 后台运行）
  → HTTP Response
```

---

## 关键设计决策

| 决策 | 方案 | 原因 |
|------|------|------|
| 应用启动 | 工厂函数 `create_app()` | 解耦 main.py 单点故障，便于测试 |
| 数据库注入 | `Depends(get_db_manager)` | 路由层统一注入，后台任务函数使用全局单例（FastAPI 规范）|
| tasks 拆分 | 5 个子模块 + router.py 聚合 | 单文件 1000+ 行 → 每文件职责单一 |
| 状态持久化 | `db.set_config("_pending_candidates")` | 避免 --reload 重启丢失 AI 对话状态 |
| HTTP 重试 | `http_utils.http_get_with_retry` | 统一指数退避，所有 TMDB/图片请求共用 |
| 错误隔离 | 任务级 `try/except → continue` | 单文件失败不阻塞整个刮削/字幕队列 |

---

*最后更新：2026-03-12*
