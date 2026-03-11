# 页面路由 - `app/`

---

## 一、主页 `app/page.tsx`

**路由：** `/`

单页应用主界面，通过 `activeView` 状态在四个视图间切换，无路由跳转。

### 视图切换

| View ID | 组件 | 说明 |
|---|---|---|
| `dashboard` | `StatsOverview` + `MiniLog` | 统计概览 + 日志流 |
| `media` | `MediaWall` | 媒体库任务列表 |
| `monitor` | `SystemMonitor` | 系统监控 |
| `settings` | `SettingsHub` | 系统设置 |

### 视觉层次

```
z-(-20)  bg-main.jpg 壁纸
z-(-10)  radial-gradient 暗场蒙版 + blur(3px)
z-10     所有实际内容（Header / Main / Footer）
z-50     Header（导航栏）
```

---

## 二、登录页 `app/auth/login/page.tsx`

**路由：** `/auth/login`

双模式页面：
- **初始化模式**：系统未初始化时，显示创建管理员账号表单
- **登录模式**：系统已初始化时，显示登录表单

**流程：**
1. 挂载时调用 `api.authStatus()` 判断模式
2. 登录成功后将 JWT 写入 `localStorage.token`
3. 跳转到 `/`

---

## 三、错误页 `app/error.tsx`

Next.js App Router 全局错误边界，捕获渲染阶段未处理异常，显示赛博朋克风格错误页并提供「重试」按钮。

---

*最后更新：2026-03-11*
