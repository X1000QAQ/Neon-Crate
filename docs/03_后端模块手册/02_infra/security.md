# security — 神盾计划安全核心

**文件路径**: `backend/app/infra/security/crypto.py`  
**核心类**: `CryptoManager`  
**单例访问**: `from app.infra.security import get_crypto_manager`

---

## 职责

提供三层安全保障：
1. **Fernet 对称加密**：保护 API 密钥等敏感配置
2. **Bcrypt 密码哈希**：管理员账号密码安全存储
3. **JWT Token**：无状态会话管理

---

## 文件说明

| 文件 | 用途 | gitignore |
|------|------|----------|
| `data/secret.key` | Fernet 主密钥，自动生成 | ✅ 已忽略 |
| `data/auth.json` | 管理员账号哈希存储 | ✅ 已忽略 |

---

## CryptoManager 方法速查

### 初始化与密钥管理

```python
crypto = CryptoManager(
    secret_key_path="data/secret.key",
    auth_path="data/auth.json"
)
# 首次启动自动生成 Fernet 密钥并持久化
# 后续启动从文件加载，保证加密数据可恢复
```

### API 密钥加解密（Fernet）

```python
cipher = crypto.encrypt_api_key("sk-xxx")   # → 加密字符串
plain  = crypto.decrypt_api_key(cipher)      # → "sk-xxx"
```

### 管理员账号

```python
crypto.is_initialized() -> bool              # 检查 auth.json 是否存在
crypto.init_admin(username, password) -> bool # 仅可执行一次
crypto.authenticate(username, password) -> bool
crypto.get_admin_username() -> Optional[str]
```

### JWT Token

```python
token = crypto.create_access_token(username)       # 有效期 7 天
username = crypto.verify_token(token)              # 失效返回 None
```

---

## 鉴权流程

```
POST /api/v1/auth/login
  → CryptoManager.authenticate(username, password)
  → Bcrypt 验证 auth.json 中的 password_hash
  → create_access_token(username)
  → 返回 JWT Token

后续请求
  → HTTP Header: Authorization: Bearer <token>
  → get_current_user() (app/api/auth.py)
  → crypto.verify_token(token)
  → 验证通过 → 路由处理函数执行
```

---

## 安全约束

- `secret.key` 文件权限自动设为 `0o600`（仅属主可读写）
- `auth.json` 文件权限自动设为 `0o600`
- JWT 使用 Fernet 密钥字节作为签名密钥，与加密密钥同源
- Token 过期后 `verify_token()` 返回 `None`，触发 HTTP 401
