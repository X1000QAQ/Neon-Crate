# NeuralLinkAlert — 断线告警弹窗

**文件路径**: `frontend/components/common/NeuralLinkAlert.tsx`  
**组件类型**: `'use client'`  
**层级**: `fixed inset-0 z-[9999]`

---

## 职责

当检测到后端断线时，覆盖全屏显示 NEURAL LINK SEVERED 告警弹窗，阻止用户继续操作，并提供重连按钮。

---

## 触发机制

```typescript
// api.ts 中的全局错误拦截
if (res.status === 0 || res.status >= 500) {
  if (typeof window !== 'undefined' && (window as any).__setLinkDown) {
    (window as any).__setLinkDown(true);
  }
}
```

`NetworkContext` 将 `setIsLinkDown` 挂载到 `window.__setLinkDown`，供 `api.ts` 在任意位置调用。

---

## 弹窗内容

```
⚠ NEURAL LINK SEVERED
警告：神经链路连接中断
[尝试重连 RECONNECT]
```

点击重连按钮：
1. `setLinkDown(false)` — 关闭弹窗
2. `window.location.reload()` — 强制刷新页面

---

## 视觉样式

- 背景：`rgba(0,0,0,0.75)` 半透明遮罩
- 弹窗：深黑底 + 红色边框 + `animate-pulse` 脉冲动画
- 阴影：`0 0 32px 8px rgba(239,68,68,0.6)` 红色外发光

---

## 依赖

```
NeuralLinkAlert
  └── context/NetworkContext (useNetwork)
```
