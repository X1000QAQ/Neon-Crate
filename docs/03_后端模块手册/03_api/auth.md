# auth — 鉴权路由

**文件路径**: `backend/app/api/auth.py`  
**路由前缀**: `/api/v1/auth`  
**JWT 保护**: ❌（鉴权路由本身无需 Token）

---

## 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/auth/status` | 检查系统是否已初始化管理员账号 |
| `POST` | `/api/v1/auth/init` | 首次初始化管理员账号（仅可执行一次）|
| `POST` | `/api/v1/auth/login` | 登录，返回 JWT Token |
| `GET` | `/api/v1/auth/verify` | 验证 Token 有效性 |

---

## 端点详情

### GET /status

```json
// 响应
{ "initialized": true, "message": "系统已初始化" }
```

### POST /init

```json
// 请求
{ "username": "admin", "password": "yourpassword" }
// 响应
{ "success": true, "message": "管理员账号创建成功" }
// 重复调用 → 400 Bad Request
```

### POST /login

```json
// 请求
{ "username": "admin", "password": "yourpassword" }
// 响应
{ "access_token": "eyJ...", "token_type": "bearer", "username": "admin" }
// 凭证错误 → 401 Unauthorized
```

### GET /verify

```
Header: Authorization: Bearer <token>
// 响应
{ "valid": true, "username": "admin" }
// Token 无效 → 401 Unauthorized
```

---

## 全局鉴权依赖

```python
# app/api/auth.py 导出
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """验证 JWT Token 并返回当前用户名，注入到所有受保护路由"""
```

`app_factory.py` 在注册业务路由时全局注入：

```python
app.include_router(
    api_router,
    prefix="/api/v1",
    dependencies=[Depends(get_current_user)]  # 全局 JWT 保护
)
```
