# AuthGuard — JWT 鉴权守卫

**文件路径**: `frontend/components/common/AuthGuard.tsx`  
**组件类型**: `'use client'`

---

## 职责

包裹所有受保护页面，在渲染前完成鉴权校验，未通过则重定向到登录页。

---

## 鉴权流程

```
路径 === '/auth/login'
  └── 直接渲染 children（登录页无需鉴权）

其他路径：
  1. api.authStatus() → initialized=false → router.push('/auth/login')
  2. localStorage.getItem('token') → null → router.push('/auth/login')
  3. token 存在 → setIsAuthenticated(true) → 渲染 children
  4. 任何异常 → router.push('/auth/login')
```

**注意**：当前实现仅检查 token 存在性，不调用 `/auth/verify`。Token 有效性由后端 API 请求失败时的 401 响应处理。

---

## 加载状态 UI

检查期间（`isChecking=true`）显示全屏量子加载动画：

```
纯黑背景 + 放射渐变 + 扫描线
  └── Loader2 旋转图标（cyber-cyan）
  └── 加载文字（t('auth_initializing')）
  └── 副标题（英文 Verifying access...）
```

---

## 触发时机

```typescript
useEffect(() => {
  checkAuth();
}, [pathname]);  // 路由变化时重新校验
```

每次 `pathname` 变化都重新执行鉴权检查。

---

## 依赖

```
AuthGuard
  ├── lib/api (authStatus)
  └── hooks/useLanguage
```
