# 安全模块手册 - `app/infra/security/`

> 路径：`backend/app/infra/security/crypto.py`

---

## 一、模块概述

**神盾计划（Project Aegis）** 安全核心。提供四项能力：
1. **Fernet 对称加密**：保护 API 密钥等敏感配置，密钥自动生成并持久化到 `data/secret.key`
2. **Bcrypt 密码哈希**：管理员账号密码安全存储
3. **JWT Token**：无状态会话管理，7 天过期
4. **管理员账号管理**：初始化 / 验证 / 读取，数据存储在 `data/auth.json`

---

## 二、核心类：`CryptoManager`

### 初始化

```python
CryptoManager(
    secret_key_path: str = "data/secret.key",
    auth_path: str = "data/auth.json"
)
```

启动时自动加载或生成 Fernet 密钥，密钥文件权限设为 `0o600`。

---

### 方法列表

| 方法 | 入参 | 返回 | 说明 |
|---|---|---|---|
| `encrypt_api_key(text)` | `str` | `str` | Fernet 加密，空字符串直接返回 |
| `decrypt_api_key(cipher)` | `str` | `str` | Fernet 解密，失败返回空字符串 |
| `get_password_hash(password)` | `str` | `str` | Bcrypt 哈希 |
| `verify_password(plain, hashed)` | `str, str` | `bool` | 验证密码 |
| `create_access_token(username)` | `str` | `str` | 生成 JWT，默认 7 天过期 |
| `verify_token(token)` | `str` | `Optional[str]` | 验证 JWT，返回 username 或 None |
| `is_initialized()` | - | `bool` | 检查 `auth.json` 是否存在 |
| `init_admin(username, password)` | `str, str` | `bool` | 首次初始化管理员（只能执行一次）|
| `authenticate(username, password)` | `str, str` | `bool` | 验证管理员登录 |
| `get_admin_username()` | - | `Optional[str]` | 获取管理员用户名 |

---

## 三、全局单例

```python
from app.infra.security import get_crypto_manager

crypto = get_crypto_manager()  # 懒初始化单例
token = crypto.create_access_token("admin")
username = crypto.verify_token(token)
```

---

## 四、文件依赖

| 文件 | 用途 | 权限 |
|---|---|---|
| `data/secret.key` | Fernet 主密钥（同时作为 JWT 签名密钥）| `0o600` |
| `data/auth.json` | 管理员用户名 + bcrypt 哈希密码 | `0o600` |

---

## 五、调用链

```
api/auth.py
  └─► get_crypto_manager()
        └─► CryptoManager
              