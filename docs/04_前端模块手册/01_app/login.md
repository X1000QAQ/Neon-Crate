# login/page.tsx — 登录页

**文件路径**: `frontend/app/auth/login/page.tsx`  
**组件类型**: `'use client'`  
**路由**: `/auth/login`

---

## 职责

处理两种场景：
- **首次访问**（系统未初始化）：展示 INITIALIZE LINK 表单，创建管理员账号
- **后续登录**（系统已初始化）：展示 INITIATE LINK 表单，JWT 登录

---

## 状态机

```
挂载
  └── api.authStatus() ──┬── initialized=true  → 登录模式
                          └── initialized=false → 初始化模式

启动动画（2.6s）
  bootPct: 0 → 100（每120ms +5）
  booting=true → false → 展示表单

表单提交
  ├── 初始化模式: api.initAuth() → api.login()
  └── 登录模式:   api.login()
        → localStorage.setItem('token', ...)
        → router.push('/')
```

---

## 启动动画

系统检测序列（SYSTEM CHECK），依次点亮四个状态指示器：

| 序号 | 图标 | 标签 | 状态文本 |
|------|------|------|----------|
| 0 | `Cpu` | CPU | NOMINAL |
| 1 | `Wifi` | NETWORK | SECURE |
| 2 | `Database` | DATABASE | ONLINE |
| 3 | `Shield` | AUTH | READY |

每个指示器在 `bootPct > index * 25` 时亮起，底部进度条同步更新。

---

## 表单字段

| 字段 | 标签 | 验证 |
|------|------|------|
| username | NEURAL_ID | `minLength=3` |
| password | QUANTUM_KEY | `minLength=6` |
| confirmPw | CONFIRM_KEY | 仅初始化模式显示，需与 password 匹配 |

---

## Glitch 效果

登录成功后每 4.5 秒触发一次 `glitch-x` CSS 动画（X 轴偏移 ±3px，持续 150ms），增强赛博朋克氛围。

---

## Token 存储

```typescript
localStorage.setItem('token', r.access_token);
localStorage.setItem('username', r.username);
```

Token 由 `AuthGuard` 在每次页面切换时校验，由 `api.ts` 在每次请求时附加到 `Authorization: Bearer` 头。

---

## 依赖

```
login/page.tsx
  ├── lib/api (authStatus / login / initAuth)
  └── hooks/useLanguage
```
