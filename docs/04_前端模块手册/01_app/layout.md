# layout.tsx — 根布局

**文件路径**: `frontend/app/layout.tsx`  
**组件类型**: Server Component（无 `'use client'`）

---

## 职责

- 定义全局 `<html>` 和 `<body>` 标签
- 挂载全局样式 `globals.css`
- 注入 `<ClientShell>` 作为客户端根组件

---

## 设计决策

| 决策 | 原因 |
|------|------|
| 保持 Server Component | 避免 SSR/客户端水合不匹配 |
| `<html lang="zh-CN">` 静态写死 | 动态语言切换由子组件 `useLanguage()` 处理，不影响 HTML 根元素 |
| 仅引入 `ClientShell` | 所有客户端逻辑集中在 `ClientShell`，布局保持纯净 |

---

## 结构

```tsx
export default function RootLayout({ children }) {
  return (
    <html lang="zh-CN">
      <head>
        <title>Neon Crate - 数据容器编排引擎</title>
        <meta name="description" content="..." />
      </head>
      <body>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
```

`{children}` 对应当前路由的 `page.tsx` 内容。

---

## 依赖

```
layout.tsx
  ├── ./globals.css
  └── components/common/ClientShell
```

→ 详见 [ClientShell.md](../02_components/common/ClientShell.md)
