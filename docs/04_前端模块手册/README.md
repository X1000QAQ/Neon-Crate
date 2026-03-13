# 前端模块手册

> **技术栈**: Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS  
> **主题风格**: Cyberpunk 2077 全息界面（霓虹青 `#00e6f6` + 标志黄 `#f9f002`）  
> **版本**: 2.0.0 — 基于 2026-03-12 代码完整梳理

---

## 目录结构

```
04_前端模块手册/
├── README.md                      ← 本文件：总目录导航
│
├── 01_app/                        ← Next.js App Router 层
│   ├── layout.md                  ← 根布局（Server Component）
│   ├── page.md                    ← 主页面（SPA 四视图导航）
│   └── login.md                   ← 登录页（初始化 + 认证）
│
├── 02_components/
│   ├── common/                    ← 通用基础组件
│   │   ├── ClientShell.md         ← 客户端壳层（全局 Provider 挂载点）
│   │   ├── AuthGuard.md           ← JWT 鉴权守卫
│   │   ├── CyberParticles.md      ← Canvas 粒子背景
│   │   ├── NeuralLinkAlert.md     ← 全屏断线告警弹窗
│   │   └── SecureImage.md         ← 带鉴权的图片组件
│   ├── media/                     ← 媒体库相关组件
│   │   ├── MediaWall.md           ← 媒体库主容器（状态管理）
│   │   ├── MediaTable.md          ← 任务卡片列表
│   │   ├── MediaToolbar.md        ← 搜索/过滤/操作工具栏
│   │   ├── MediaPagination.md     ← 分页控件
│   │   ├── StatsOverview.md       ← 统计卡片 + 指令中心
│   │   ├── MiniLog.md             ← 仪表盘日志流（轻量）
│   │   └── SystemMonitor.md       ← 全功能日志监控（Monitor 视图）
│   ├── settings/                  ← 设置相关组件
│   │   └── SettingsHub.md         ← 设置中心（Tab 导航 + 6 个子模块）
│   └── ai/                        ← AI 助手组件
│       └── AiSidebar.md           ← Neural Core 侧边栏
│
├── 03_lib/                        ← 工具函数库
│   ├── api.md                     ← API 客户端（全量接口封装）
│   ├── i18n.md                    ← 国际化字典（zh/en）
│   └── utils.md                   ← 工具函数（cn / formatDate）
│
├── 04_types/
│   └── index.md                   ← TypeScript 类型定义
│
├── 05_context_hooks/
│   ├── NetworkContext.md          ← 全局断线状态 Context
│   └── useLanguage.md             ← 多语言 Hook
│
└── 06_styles/
    ├── globals.md                 ← 全局 CSS（字体/颜色/动画/滚动条）
    └── tailwind.md                ← Tailwind 扩展配置
```

---

## 架构分层

```
┌──────────────────────────────────────────────────┐
│             app/layout.tsx (Server)              │
│         <html> + <ClientShell>{page}</ClientShell>│
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│              ClientShell (Client)                │
│  NetworkProvider → CyberParticles → AuthGuard    │
│    → {children} + AiSidebar                      │
│  → NeuralLinkAlert                               │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│   app/page.tsx — 四视图 SPA（activeView 状态）    │
│  dashboard │ media │ monitor │ settings           │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│            components/ 各业务组件                 │
│  StatsOverview · MediaWall · SystemMonitor        │
│  SettingsHub · AiSidebar                         │
└──────────────────┬───────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────┐
│               lib/api.ts                         │
│  fetch → /api/* → next.config.js rewrite         │
│        → http://localhost:8000/api/*              │
└──────────────────────────────────────────────────┘
```

---

## 视图路由

| 路径 | 组件 | 说明 |
|------|------|------|
| `/` | `app/page.tsx` | 主应用（含 4 个内部视图）|
| `/auth/login` | `app/auth/login/page.tsx` | 登录/初始化页 |

SPA 内部视图切换不产生路由跳转，通过 `activeView` 状态控制。

---

## 全局配色变量

| CSS 变量 | 值 | 用途 |
|----------|-----|------|
| `--cyber-cyan` | `#00e6f6` | 主色（边框/文字/图标）|
| `--cyber-yellow` | `#f9f002` | 强调色（标题/高亮）|
| `--cyber-red` | `#ff013c` | 危险色（错误/删除）|
| `--cyber-bg` | `#000000` | 背景底色 |
| `--cyber-border` | `#8ae66e` | 辅助绿色边框 |

---

## 技术依赖

| 包 | 版本 | 用途 |
|----|------|------|
| `next` | ^14.1.0 | App Router / SSR / API Rewrite |
| `react` | ^18.2.0 | 核心框架 |
| `tailwindcss` | ^3.4.1 | 原子化 CSS |
| `lucide-react` | ^0.344.0 | 图标库 |
| `clsx` + `tailwind-merge` | latest | `cn()` 工具函数 |

---

*最后更新：2026-03-12*
