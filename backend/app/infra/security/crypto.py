"""
神盾计划 (Project Aegis) - 安全核心模块

工业级加密与鉴权系统：
1. Fernet 对称加密：保护 API 密钥等敏感配置
2. Bcrypt 密码哈希：管理员账号密码安全存储
3. JWT Token：无状态会话管理
4. 自动密钥生成与持久化
"""
import os
import json
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet
from passlib.context import CryptContext
import jwt


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
        """初始化或加载 Fernet 密钥"""
        if os.path.exists(self.secret_key_path):
            with open(self.secret_key_path, 'rb') as f:
                key = f.read()
            print(f"[OK] [SECURITY] Loaded encryption key: {self.secret_key_path}")
        else:
            key = Fernet.generate_key()
            with open(self.secret_key_path, 'wb') as f:
                f.write(key)
            try:
                os.chmod(self.secret_key_path, 0o600)
            except Exception:
                pass
            print(f"[OK] [SECURITY] Generated new encryption key: {self.secret_key_path}")
        
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
            print(f"[ERROR] [SECURITY] 解密失败: {e}")
            return ""
    
    def get_password_hash(self, password: str) -> str:
        """生成密码哈希"""
        return self.pwd_context.hash(password)
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """验证密码"""
        return self.pwd_context.verify(plain_password, hashed_password)
    
    def create_access_token(self, username: str, expires_delta: Optional[timedelta] = None) -> str:
        """生成 JWT Access Token"""
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
        """验证 JWT Token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[self.jwt_algorithm])
            username: str = payload.get("sub")
            return username
        except jwt.ExpiredSignatureError:
            print("[WARNING] [SECURITY] Token 已过期")
            return None
        except jwt.InvalidTokenError:
            print("[WARNING] [SECURITY] Token 无效")
            return None
    
    def is_initialized(self) -> bool:
        """检查系统是否已初始化管理员账号"""
        return os.path.exists(self.auth_path)
    
    def init_admin(self, username: str, password: str) -> bool:
        """初始化管理员账号"""
        if self.is_initialized():
            print("[WARNING] [SECURITY] 管理员账号已存在")
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
        
        print(f"[OK] [SECURITY] 管理员账号已创建: {username}")
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
