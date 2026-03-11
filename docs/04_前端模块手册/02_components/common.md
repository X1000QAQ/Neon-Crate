# 通用组件 - `components/common/`

---

## 一、`AuthGuard.tsx`

路由鉴权守卫，包裹所有页面内容。

**检查流程：**
1. 若当前路径为 `/auth/login`，直接放行渲染
2. 调用 `api.authStatus()` 检查系统是否初始化，未初始化则跳转登录
3. 检查 `localStorage.token`，无 Token 则跳转登录
4. 通过则渲染子组件

**加载态：** 检查期间显示赛博朋克风格全屏 Loading（`Loader2` 旋转图标）

**注意：** `authStatus` 调用不带 JWT（系统未初始化时没有 Token），其余检查在客户端完成。

---

## 二、`NeuralLinkAlert.tsx`

全局网络断链弹窗，`z-[9999]` 全屏覆盖。

- 监听 `NetworkContext.isLinkDown`
- `isLinkDown=false` 时不渲染（`return null`）
- 「重连」按钮：`setLinkDown(false)` + `window.location.reload()`

**触发链路：**
```
api.ts secureFetch() → notifyLinkDown()
  → window.__setLinkDown(true)
  → NetworkContext.isLinkDown = true
  → NeuralLinkAlert 显示
```

---

## 三、`SecureImage.tsx`

安全图片代理组件，将本地图片路径转为后端代理 URL。

```typescript
// 本地路径 → /api/v1/public/image?path=...
```

防止前端直接拼接文件系统路径，所有图片经后端 `GET /api/v1/public/image` 中转。

---

## 四、`CyberParticles.tsx`

Canvas 背景粒子特效，固定定位 `z-0`，纯视觉装饰。

- 使用 `requestAnimationFrame` 驱动动画
- 粒子颜色：`rgba(0, 230, 246, ...)` (cyber-cyan)
- 组件卸载时自动取消动画帧，无内存泄漏

---

*最后更新：2026-03-11*
