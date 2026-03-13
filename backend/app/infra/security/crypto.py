"""
神盾计划 (Project Aegis) - 安全核心模块

设计目标：
- 提供工业级加密与鉴权能力
- 保护敏感配置和用户密码
- 支持无状态会话管理

核心功能：

1. Fernet 对称加密
   - 用途：保护 API 密钥等敏感配置
   - 算法：AES-128-CBC + HMAC-SHA256
   - 密钥管理：自动生成并持久化到 data/secret.key
   - 权限：文件权限设置为 0o600（仅所有者可读写）

2. Bcrypt 密码哈希
   - 用途：管理员账号密码安全存储
   - 算法：Bcrypt（自适应哈希，防止暴力破解）
   - 存储：密码哈希存储在 data/auth.json
   - 验证：使用 passlib 库进行密码验证

3. JWT Token
   - 用途：无状态会话管理
   - 算法：HS256（HMAC-SHA256）
   - 有效期：7 天（可配置）
   - 载荷：包含用户名、过期时间、签发时间

4. 自动密钥生成
   - 首次启动：自动生成 Fernet 密钥
   - 持久化：保存到 data/secret.key
   - 复用：后续启动从文件加载

安全特性：
- 密钥文件权限：0o600（仅所有者可读写）
- 密码哈希：Bcrypt 自适应哈希，防止彩虹表攻击
- Token 过期：JWT 自动过期，防止长期有效 Token 泄露
- 单例模式：全局唯一实例，避免重复初始化

使用方式：
```python
from app.infra.security import get_crypto_manager

crypto = get_crypto_manager()

# 加密 API 密钥
encrypted = crypto.encrypt_api_key("my_secret_key")

# 解密 API 密钥
decrypted = crypto.decrypt_api_key(encrypted)

# 生成密码哈希
password_hash = crypto.get_password_hash("password123")

# 验证密码
is_valid = crypto.verify_password("password123", password_hash)

# 生成 JWT Token
token = crypto.create_access_token("admin")

# 验证 JWT Token
username = crypto.verify_token(token)
```
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet
from passlib.context import CryptContext
import jwt

logger = logging.getLogger(__name__)


class CryptoManager:
    """加密管理器 - 神盾计划核心引擎"""

    def __init__(self, secret_key_path: str = "data/secret.key", auth_path: str = "data/auth.json"):
        self.secret_key_path = secret_key_path
        self.auth_path = auth_path

        os.makedirs(os.path.dirname(secret_key_path), exist_ok=True)

        self.fernet = self._init_fernet()
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        self.jwt_secret = self._get_jwt_secret()
        self.jwt_algorithm = "HS256"
        self.jwt_expire_days = 7

    def _init_fernet(self) -> Fernet:
        """
        初始化或加载 Fernet 对称加密密钥

        首次初始化：
        - 自动生成 32 字节随机密钥（Fernet.generate_key）
        - 保存到 data/secret.key 文件
        - 设置文件权限 0o600（仅所有者可读写）

        后续加载：
        - 从 data/secret.key 文件读取密钥
        - 密钥不变，确保历史加密数据可解密

        注意事项：
        - 密钥丢失 = 所有加密数据永久无法解密
        - 建议定期备份 data/secret.key
        - Docker 部署时应将 data/ 目录挂载到宿主机
        """
        if os.path.exists(self.secret_key_path):
            with open(self.secret_key_path, 'rb') as f:
                key = f.read()
            logger.info(f"[SECURITY] Loaded encryption key: {self.secret_key_path}")
        else:
            key = Fernet.generate_key()
            with open(self.secret_key_path, 'wb') as f:
                f.write(key)
            try:
                os.chmod(self.secret_key_path, 0o600)
            except Exception:
                pass
            logger.info(f"[SECURITY] Generated new encryption key: {self.secret_key_path}")

        return Fernet(key)

    def _get_jwt_secret(self) -> str:
        """获取 JWT 签名密钥"""
        with open(self.secret_key_path, 'rb') as f:
            return f.read().decode('utf-8')

    def encrypt_api_key(self, text: str) -> str:
        """加密 API 密钥"""
        if not text or text.strip() == "":
            return ""
        encrypted = self.fernet.encrypt(text.encode('utf-8'))
        return encrypted.decode('utf-8')

    def decrypt_api_key(self, cipher: str) -> str:
        """解密 API 密钥"""
        if not cipher or cipher.strip() == "":
            return ""
        try:
            decrypted = self.fernet.decrypt(cipher.encode('utf-8'))
            return decrypted.decode('utf-8')
        except Exception as e:
            logger.error(f"[SECURITY] 解密失败: {e}")
            return ""

    def get_password_hash(self, password: str) -> str:
        """生成密码哈希"""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)

    def create_access_token(self, username: str, expires_delta: Optional[timedelta] = None) -> str:
        """
        生成 JWT Access Token

        JWT 载荷：
        - sub：用户名（subject）
        - exp：过期时间（expiration，默认 7 天后）
        - iat：签发时间（issued at）

        安全特性：
        - 使用 Fernet 密钥作为 JWT 签名密钥
        - HS256 算法：HMAC-SHA256，对称签名
        - 自动过期：Token 过期后需重新登录
        """
        if expires_delta is None:
            expires_delta = timedelta(days=self.jwt_expire_days)

        expire = datetime.utcnow() + expires_delta
        payload = {
            "sub": username,
            "exp": expire,
            "iat": datetime.utcnow()
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token

    def verify_token(self, token: str) -> Optional[str]:
        """
        验证 JWT Token 并返回用户名

        验证内容：
        - 签名有效性：防止 Token 被篡改
        - 过期时间：自动拒绝过期 Token

        Returns:
            str: 用户名（Token 有效时）
            None: Token 无效或已过期
        """
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            username: str = payload.get("sub")
            return username
        except jwt.ExpiredSignatureError:
            logger.warning("[SECURITY] Token 已过期")
            return None
        except jwt.InvalidTokenError:
            logger.warning("[SECURITY] Token 无效")
            return None

    def is_initialized(self) -> bool:
        """检查系统是否已初始化管理员账号"""
        return os.path.exists(self.auth_path)

    def init_admin(self, username: str, password: str) -> bool:
        """初始化管理员账号"""
        if self.is_initialized():
            logger.warning("[SECURITY] 管理员账号已存在")
            return False

        password_hash = self.get_password_hash(password)
        auth_data = {
            "username": username,
            "password_hash": password_hash,
            "created_at": datetime.now().isoformat()
        }

        with open(self.auth_path, 'w', encoding='utf-8') as f:
            json.dump(auth_data, f, indent=4, ensure_ascii=False)

        try:
            os.chmod(self.auth_path, 0o600)
        except Exception:
            pass

        logger.info(f"[SECURITY] 管理员账号已创建: {username}")
        return True

    def authenticate(self, username: str, password: str) -> bool:
        """验证管理员账号"""
        if not self.is_initialized():
            return False

        with open(self.auth_path, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)

        if auth_data.get("username") != username:
            return False

        return self.verify_password(password, auth_data.get("password_hash", ""))

    def get_admin_username(self) -> Optional[str]:
        """获取管理员用户名"""
        if not self.is_initialized():
            return None

        with open(self.auth_path, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)

        return auth_data.get("username")


# 全局单例
_crypto_manager: Optional[CryptoManager] = None


def get_crypto_manager() -> CryptoManager:
    """获取全局加密管理器实例"""
    global _crypto_manager
    if _crypto_manager is None:
        _crypto_manager = CryptoManager()
    return _crypto_manager
