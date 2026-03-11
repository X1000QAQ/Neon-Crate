# 鉴权端点手册 - `app/api/auth.py`

> 路径：`backend/app/api/auth.py`
> 路由前缀：`/api/v1/auth`

---

## 一、模块概述

**神盾计划（Project Aegis）** 鉴权路由。提供系统初始化、登录、Token 验证四个接口，以及全局 JWT 依赖注入函数 `get_current_user()`。

---

## 二、接口列表

### `GET /auth/status`

检查系统是否已初始化管理员账号。

**响应：`AuthStatusResponse`**
```json
{
  "initialized": true,
  "message": "系统已初始化"
}
```

### `POST /auth/init`

首次初始化管理员账号（**仅允许执行一次**）。

**请求体：`InitRequest`**
```json
{
  "username": "admin",
  "password": "123456"
}
```

**限制：** 若已初始化，返回 `HTTP 400`。

### `POST /auth/login`

登录验证，返回 JWT Token。

**响应：`TokenResponse`**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "username": "admin"
}
```

**错误：**
- `HTTP 400`：系统未初始化
- `HTTP 401`：用户名或密码错误

### `GET /auth/verify`

验证 Token 有效性。需在请求头携带 `Authorization: Bearer <token>`。

---

## 三、依赖注入：`get_current_user()`

```python
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
```

- 注入到所有受保护路由（在 `main.py` 中通过 `dependencies=[Depends(get_current_user)]` 全局挂载）
- Token 无效或过期时返回 `HTTP 401`
- 返回当前登录的用户名字符串

---

## 四、调用链

```
POST /auth/login
  └─► get_crypto_manager()
        ├─► authenticate(username, password)   # bcrypt 校验
        └─► create_access_token(username)      # 生成 JWT

受保护路由（全局）
  └─► get_current_user()  [Depends]
        └─► verify_token(token)               # JWT 校验
```

---

## 五、注意事项

- Token 存储在前端 `localStorage`，由 `AuthGuard.tsx` 在每次路由跳转时校验
- Token 默认 7 天过期，过期后需重新登录
- 系统仅支持**单管理员账号**，不支持多用户

---

*最后更新：2026-03-11*
