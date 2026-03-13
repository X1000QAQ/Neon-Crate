# NetworkContext — 全局断线状态

**文件路径**: `frontend/context/NetworkContext.tsx`  
**组件类型**: `'use client'`

---

## 职责

通过 React Context 在全局共享后端连接状态，并将 `setLinkDown` 函数挂载到 `window` 对象，使 `api.ts` 可在 Context 树外部触发断线告警。

---

## Context 接口

```typescript
interface NetworkContextValue {
  isLinkDown: boolean;            // 当前是否断线
  setLinkDown: (v: boolean) => void;
}
```

---

## window 挂载机制

```typescript
useEffect(() => {
  (window as any).__setLinkDown = setIsLinkDown;
  return () => { delete (window as any).__setLinkDown; };
}, []);
```

`api.ts` 检测到 HTTP 500 / 网络错误时调用 `window.__setLinkDown(true)`，触发 `NeuralLinkAlert` 弹窗。

---

## 使用方式

```typescript
// 在组件内
import { useNetwork } from '@/context/NetworkContext';
const { isLinkDown, setLinkDown } = useNetwork();

// 在 api.ts（Context 树外部）
(window as any).__setLinkDown?.(true);
```

---

## 挂载位置

`NetworkProvider` 在 `ClientShell` 中作为最外层 Provider：

```tsx
<NetworkProvider>          ← 最外层
  <CyberParticles />
  <AuthGuard>...</AuthGuard>
  <NeuralLinkAlert />     ← 消费 useNetwork()
</NetworkProvider>
```
