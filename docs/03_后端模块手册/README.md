# 模块手册（最新版）

> 基于 2026-03-11 重构后的最新代码生成，与旧版 `04_模块手册` 的主要差异：
>
> - `scraper/cleaner.py`：完全去除硬编码正则，改为从数据库读取（与 AI 人格架构一致）
> - `db_manager.py`：默认15条正则直接硬编码在注入逻辑中，不再依赖 `MediaCleaner` 提取
> - `RegexLab.tsx`：改为接收 `config/setConfig` props，不再独立管理状态和 API 调用
> - 后端断链检查：无 `temp_cleaner` 外部引用，无旧 pattern 属性遗留

---

## 目录结构

```
04_后端模块手册/
├── main.md             # 应用入口 + 自动巡逻流水线
├── 01_infra/
│   ├── config.md       # 环境变量配置模块
│   ├── database.md     # SQLite 数据库管理器
│   └── security.md     # 加密/JWT/鉴权
├── 02_api/
│   ├── agent.md        # AI 对话端点（新增）
│   ├── auth.md         # 鉴权端点
│   ├── system.md       # 系统状态端点
│   └── tasks.md        # 核心任务端点
├── 03_services/
│   ├── ai_agent.md     # AI Agent 决策层
│   ├── downloader.md   # Servarr 下载器
│   ├── metadata.md     # TMDB 元数据适配器
│   ├── organizer.md    # 文件归档整理器
│   ├── scraper.md      # 扫描引擎（重构后）
│   └── subtitle.md     # 字幕查找服务
└── 04_models/
    └── models.md       # 领域模型
```

---

*最后更新：2026-03-11*
