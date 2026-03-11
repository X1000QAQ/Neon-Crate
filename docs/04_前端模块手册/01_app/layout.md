# 根布局与客户端外壳 - `app/layout.tsx` + `ClientShell.tsx`

---

## 一、`app/layout.tsx`

根布局，挂载全局字体、CSS、元数据，并包裹 `ClientShell`。

```
RootLayout
  └─► ClientShell
        ├─► NetworkProvider     # 全局网络断链状态
        ├─► CyberParticles      # 背景粒子特效
        ├─► AuthGuard           # JWT 鉴权守卫
        │     ├─► {children}    # 页面内容
        │     └─► AiSidebar    # AI 侧边栏（悬浮）
        └─► NeuralLinkAlert     # 断链全局弹窗
```

**字体加载：** `Advent Pro`（标题）、`Share Tech Mono`（代码/等宽）

---

## 二、`ClientShell.tsx`

```typescript
export default function ClientShell({ children })
```

客户端组件壳，将所有需要 `'use client'` 的 Provider 和全局组件集中在此，避免污染 Server Component 根布局。

**组合顺序：**
1. `NetworkProvider` — 最外层，提供 `isLinkDown` 全局状态
2. `CyberParticles` — 背景粒子（Canvas，固定定位，`z-0`）
3. `AuthGuard` — 鉴权守卫，内部渲染页面内容 + `AiSidebar`
4. `NeuralLinkAlert` — 断链警告弹窗，监听 `NetworkContext`

---

*最后更新：2026-03-11*
