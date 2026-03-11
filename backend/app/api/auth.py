"""
神盾计划 (Project Aegis) - 鉴权路由

提供三个核心接口：
1. GET /status - 检查系统是否已初始化
2. POST /init - 首次初始化管理员账号
3. POST /login - 登录验证并返回 JWT Token
4. GET /verify - 验证 Token 有效性
"""
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
security = HTTPBearer()


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


# 依赖注入：全局 JWT 验证
def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """验证 JWT Token 并返回当前用户名"""
    crypto = get_crypto_manager()
    username = crypto.verify_token(credentials.credentials)
    
    if username is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return username
