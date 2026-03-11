# 前端模块手册

> 技术栈：Next.js 14 (App Router) + TypeScript + Tailwind CSS
> 路径：`frontend/`

---

## 断链 / 僵尸代码检查结论

### 已确认问题

| 位置 | 问题 | 严重度 |
|---|---|---|
| `types/index.ts` | `auto_process_enabled` 字段存在于前端类型定义，但后端 `SystemSettings` 无此字段 | 低（多余字段，不影响运行）|
| `types/index.ts` | `Task.status` 包含 `'success'`，后端实际只有 `'scraped'`，两者不一致 | 中（类型不准确，可能导致状态判断失效）|
| `types/index.ts` | `Task.sub_status` 包含 `'success'`，后端实际为 `'scraped'` | 中（同上）|
| `api.ts` | `purgeAllTasks()` 发送 `{confirm: 'CONFIRM'}` 但后端 `PurgeRequest` 只接受 `{status: string}` | 中（API 参数不匹配）|

### 无问题

- 所有 `import` 路径均有对应文件，无断链
- `RegexLab` 已正确通过 `props` 接收 `config/setConfig`，不再独立管理状态和 API 调用
- `NetworkContext` / `NeuralLinkAlert` / `__setLinkDown` 全局挂载链路完整
- `useLanguage` hook 与 `i18n.ts` 联动正确
- `AuthGuard` Token 校验逻辑完整

---

## 目录结构

```
05_前端模块手册/
├── 01_app/
│   ├── layout.md       # 根布局 + ClientShell
│   └── pages.md        # 页面路由（主页 / 登录页 / 错误页）
├── 02_components/
│   ├── common.md       # 通用组件（AuthGuard / NeuralLinkAlert / SecureImage / CyberParticles）
│   ├── ai.md           # AI 侧边栏
│   ├── media.md        # 媒体库组件
│   └── settings.md     # 设置面板组件
├── 03_lib/
│   ├── api.md          # API 客户端
│   ├── i18n.md         # 国际化
│   └── utils.md        # 工具函数
├── 04_types/
│   └── types.md        # 类型定义
└── 05_context_hooks/
    └── context_hooks.md # Context + Hooks
```

---

*最后更新：2026-03-11*
