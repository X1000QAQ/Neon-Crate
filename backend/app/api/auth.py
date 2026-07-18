"""
鉴权路由 - 初始化、登录、Token 校验与全局守卫。

职责：
- 暴露系统初始化状态、首次管理员创建、登录和 Token 校验接口。
- 提供 `get_current_user` 全局依赖，供应用工厂保护所有业务路由。
- 将密码哈希、JWT 签发和 Token 验证委托给 `CryptoManager`。

安全机制：
- 首次初始化只允许执行一次，防止重复创建管理员账号。
- 登录成功后签发 Bearer JWT，前端通过 Authorization 头访问业务接口。
- `HTTPBearer(auto_error=False)` 让缺失凭据统一走 401，避免把未认证误报为 403。

路由边界：
- 本模块不直接读写业务任务、媒体库或配置仓储。
- 修改状态码、响应结构或守卫依赖会影响前端登录态和全局 API 访问。
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
async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """验证 Token 有效性"""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing authorization token",
            headers={"WWW-Authenticate": "Bearer"},
        )
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
