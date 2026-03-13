# ClientShell — 客户端壳层

**文件路径**: `frontend/components/common/ClientShell.tsx`  
**组件类型**: `'use client'`

---

## 职责

作为全局客户端根组件，统一挂载所有全局 Provider 和常驻 UI。

---

## 渲染树

```tsx
<NetworkProvider>          ← 全局断线状态 Context
  <CyberParticles />       ← Canvas 粒子背景（z-0，全屏固定）
  <AuthGuard>              ← JWT 鉴权守卫
    {children}             ← 当前路由页面内容
    <AiSidebar />          ← Neural Core AI 侧边栏（固定定位）
  </AuthGuard>
  <NeuralLinkAlert />     ← 全屏断线告警弹窗（z-9999）
</NetworkProvider>
```

---

## 设计决策

| 决策 | 原因 |
|------|------|
| `CyberParticles` 在 `AuthGuard` 外 | 粒子背景在登录页也需显示 |
| `AiSidebar` 在 `AuthGuard` 内 | 登录页不显示 AI 侧边栏（组件内部检测 `/auth/login` 路径后 return null）|
| `NeuralLinkAlert` 在最外层 | 断线告警需覆盖所有内容（z-9999）|

---

## 依赖

```
ClientShell
  ├── context/NetworkContext (NetworkProvider)
  ├── components/common/CyberParticles
  ├── components/common/AuthGuard
  ├── components/common/NeuralLinkAlert
  └── components/ai/AiSidebar
```
