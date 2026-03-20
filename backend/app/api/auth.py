"""
神盾计划 (Project Aegis) - 鉴权路由

设计目标：
- 提供完整的认证授权流程
- 保护 API 端点免受未授权访问
- 支持首次初始化和密码重置

核心接口：
1. GET /status - 检查系统是否已初始化
2. POST /init - 首次初始化管理员账号（仅允许执行一次）
3. POST /login - 登录验证并返回 JWT Token
4. GET /verify - 验证 Token 有效性

安全机制：
- Bcrypt 密码哈希：防止密码泄露
- JWT Token：无状态会话管理，7 天有效期
- 单次初始化：防止重复创建管理员账号
- 全局依赖注入：get_current_user 保护所有业务路由

认证流程：
1. 首次访问：检查 /status，若未初始化则调用 /init
2. 登录：调用 /login 获取 JWT Token
3. 访问 API：在 Authorization 头中携带 Bearer Token
4. Token 验证：每次请求自动验证 Token 有效性

依赖注入：
- get_current_user：全局 JWT 验证依赖
- 所有业务路由自动继承此依赖
- 无需在每个路由手动添加认证逻辑
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.infra.security import get_crypto_manager
from app.models.domain_system import (
    AuthStatusResponse,
    TokenResponse,
    LoginRequest,
    InitRequest
)

router = APIRouter()
# auto_error=False：缺少 Authorization 头时不由 HTTPBearer 抛 403，而是 credentials=None，
# 由 get_current_user 统一返回 401（未认证语义），与 Bearer 守卫契约一致。
security = HTTPBearer(auto_error=False)


@router.get("/status", response_model=AuthStatusResponse)
async def check_auth_status():
    """检查系统是否已初始化管理员账号"""
    crypto = get_crypto_manager()
    initialized = crypto.is_initialized()
    
    return AuthStatusResponse(
        initialized=initialized,
        message="系统已初始化" if initialized else "系统未初始化，请先创建管理员账号"
    )


@router.post("/init")
async def init_admin(request: InitRequest):
    """首次初始化管理员账号（仅允许执行一次）"""
    crypto = get_crypto_manager()
    
    if crypto.is_initialized():
        raise HTTPException(status_code=400, detail="系统已初始化，禁止重复创建账号")
    
    success = crypto.init_admin(request.username, request.password)
    
    if not success:
        raise HTTPException(status_code=500, detail="初始化失败")
    
    return {"success": True, "message": "管理员账号创建成功"}


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """登录验证并返回 JWT Token"""
    crypto = get_crypto_manager()
    
    if not crypto.is_initialized():
        raise HTTPException(status_code=400, detail="系统未初始化")
    
    if not crypto.authenticate(request.username, request.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    token = crypto.create_access_token(request.username)
    
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        username=request.username
    )


@router.get("/verify")
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证 Token 有效性"""
    crypto = get_crypto_manager()
    username = crypto.verify_token(credentials.credentials)
    
    if username is None:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    
    return {"valid": True, "username": username}


# ==========================================
# 🔐 全局 JWT 依赖注入（Global Auth Guard）
# ==========================================
# 设计目标：保护所有业务路由，无需在每个路由单独添加认证逻辑
# 
# 使用方式：
# - app_factory.py 通过 dependencies=[Depends(get_current_user)] 注入
# - 所有业务路由自动继承此依赖
# - 返回当前用户名，可在路由中使用
# 
# 认证流程：
# 1. 从 Authorization 头提取 Bearer Token
# 2. 调用 CryptoManager.verify_token 验证签名和过期时间
# 3. 返回用户名（验证通过）或抛出 401 异常（验证失败）
# ==========================================
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """
    验证 JWT Token 并返回当前用户名（全局守卫）

    守卫语义：
    - HTTPBearer(auto_error=False) 下无头时 credentials 为 None
    - None 与无效 token 一律 401，统一为「未认证」
    - 与 403「已认证但无权限」区分，驱动客户端重登
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    crypto = get_crypto_manager()
    username = crypto.verify_token(credentials.credentials)

    if username is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return username
