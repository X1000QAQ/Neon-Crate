"""
settings_router.py - 配置管理路由

包含：
1. get_settings() — GET /settings
2. update_settings() — POST /settings
3. reset_settings() — POST /settings/reset
"""
import logging

from fastapi import APIRouter, HTTPException

from app.api.v1.deps import DbDep
from app.models.domain_system import SettingsConfig, ResetSettingsRequest
from app.api.v1.endpoints.tasks._shared import _update_library_counts

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/settings", response_model=SettingsConfig)
async def get_settings(db: DbDep):
    """
    GET /settings - 获取完整系统配置
    
    功能说明：
    - 返回完整的系统配置（settings + paths）
    - 不脱敏：前端负责隐藏敏感信息
    - 支持编辑：用户可以修改已保存的密钥
    
    为什么不脱敏？
    - 前端在显示时用 *** 替换敏感信息
    - 编辑时需要获取真实值，否则无法修改
    - 安全性：通过 HTTPS 传输，前端不缓存
    
    返回结构：
    - settings: 系统设置（API 密钥、质量配置等）
    - paths: 路径配置（下载目录、媒体库目录等）
    """
    config = db.get_all_config()

    # 确保返回正确的结构
    if "settings" not in config:
        config["settings"] = {}
    if "paths" not in config:
        config["paths"] = []

    # 🔧 修复：不再脱敏，让前端负责隐藏敏感信息
    # 前端会在显示时用 *** 替换，但编辑时可以获取真实值
    # 这样用户可以编辑已保存的密钥

    return config


@router.post("/settings")
async def update_settings(config: SettingsConfig, db: DbDep):
    """
    更新系统配置

    功能说明：
    - 接收前端发来的完整配置对象
    - 持久化保存到 config.json
    - 执行路径校验（如果配置了路径，则必须有1个电影库和1个剧集库）

    参数：
    - config: 包含 settings 和 paths 的完整配置对象

    返回：
    - success: 是否成功
    - message: 操作结果描述
    """
    # 转换为字典
    config_dict = {
        "settings": config.settings.model_dump(),
        "paths": [p.model_dump() for p in config.paths]
    }

    # 防御性编程：先校验，全部通过后才写盘
    # 校验：如果配置了路径，则必须有且仅有1个电影库和1个剧集库
    paths = config_dict.get("paths", [])
    
    # 只有当 paths 不为空时才进行校验
    if paths:
        active_libs = [
            p for p in paths
            if str(p.get("type", "")).strip().lower() in ["library", "media", "storage"]
            and p.get("enabled", True)
        ]
        movie_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "movie"]
        tv_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "tv"]

        if len(movie_libs) > 1 or len(tv_libs) > 1:
            raise HTTPException(
                status_code=400,
                detail="[ERROR] [配置错误] 系统规定同时只能开启 1个电影媒体库 和 1个剧集媒体库！"
            )
        if len(movie_libs) == 0:
            raise HTTPException(
                status_code=400,
                detail="[ERROR] [配置错误] 缺少处于开启状态的 Movie (电影) 媒体库！"
            )
        if len(tv_libs) == 0:
            raise HTTPException(
                status_code=400,
                detail="[ERROR] [配置错误] 缺少处于开启状态的 TV (剧集) 媒体库！"
            )

    # 校验全部通过，执行写盘
    try:
        db.save_all_config(config_dict)
        logger.info("[API] 系统配置已更新并持久化")
        
        # 🔧 关键修复：配置保存后立即重新计算媒体库数量缓存
        # 防止用户修改媒体库路径后，仪表盘显示为0的问题
        _update_library_counts()
        logger.info("[API] 媒体库数量缓存已更新")
        
        return {"success": True, "message": "配置已成功保存"}
    except Exception as e:
        logger.error(f"[API] 保存系统配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存系统配置失败: {str(e)}")


@router.post("/settings/verify-key")
async def verify_api_key(payload: dict, db: DbDep):
    """
    POST /tasks/settings/verify-key - 验证 API 密钥有效性
    
    功能说明：
    - 验证用户输入的 API 密钥是否有效
    - 不返回密钥本身，只返回验证结果
    - 支持多种 API 类型
    
    支持的密钥类型：
    - tmdb_api_key：TMDB API 密钥
    - sonarr_api_key：Sonarr API 密钥
    - radarr_api_key：Radarr API 密钥
    - os_api_key：OpenSubtitles API 密钥
    
    验证策略：
    - TMDB：调用搜索 API 测试
    - Sonarr/Radarr：调用 /api/v3/system/status 测试
    - OpenSubtitles：检查密钥长度和格式（无公开验证端点）
    
    参数：
    - key_type: 密钥类型
    - key_value: 密钥值
    - url: 服务地址（Sonarr/Radarr 需要）
    
    返回：
    - valid: 密钥是否有效
    """
    import httpx
    
    key_type = payload.get("key_type", "").strip()
    key_value = payload.get("key_value", "").strip()
    url = payload.get("url", "").strip()
    
    if not key_type or not key_value:
        raise HTTPException(status_code=400, detail="Missing key_type or key_value")
    
    try:
        if key_type == "tmdb_api_key":
            # TMDB 验证
            from app.services.metadata.adapters import TMDBAdapter
            adapter = TMDBAdapter(api_key=key_value)
            results = adapter.search_movie(query="test", year=None)
            logger.info(f"[API] TMDB 密钥验证成功")
            return {"valid": True}
        
        elif key_type == "sonarr_api_key":
            # Sonarr 验证
            if not url:
                url = db.get_config("sonarr_url", "").strip()
            
            if not url:
                logger.warning(f"[API] Sonarr URL 未配置")
                return {"valid": False}
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    f"{url.rstrip('/')}/api/v3/system/status",
                    headers={"X-Api-Key": key_value},
                    timeout=10.0
                )
                is_valid = resp.status_code == 200
                if is_valid:
                    logger.info(f"[API] Sonarr 密钥验证成功")
                else:
                    logger.warning(f"[API] Sonarr 密钥验证失败: HTTP {resp.status_code}")
                return {"valid": is_valid}
        
        elif key_type == "radarr_api_key":
            # Radarr 验证
            if not url:
                url = db.get_config("radarr_url", "").strip()
            
            if not url:
                logger.warning(f"[API] Radarr URL 未配置")
                return {"valid": False}
            
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(
                    f"{url.rstrip('/')}/api/v3/system/status",
                    headers={"X-Api-Key": key_value},
                    timeout=10.0
                )
                is_valid = resp.status_code == 200
                if is_valid:
                    logger.info(f"[API] Radarr 密钥验证成功")
                else:
                    logger.warning(f"[API] Radarr 密钥验证失败: HTTP {resp.status_code}")
                return {"valid": is_valid}
        
        elif key_type == "os_api_key":
            # OpenSubtitles 验证（简单检查：密钥长度和格式）
            # OpenSubtitles 没有公开的验证端点，所以只做基础检查
            is_valid = len(key_value) >= 20  # OpenSubtitles API Key 通常较长
            if is_valid:
                logger.info(f"[API] OpenSubtitles 密钥格式验证成功")
            else:
                logger.warning(f"[API] OpenSubtitles 密钥格式验证失败: 长度不足")
            return {"valid": is_valid}
        
        else:
            logger.warning(f"[API] 未知的密钥类型: {key_type}")
            return {"valid": False}
    
    except httpx.TimeoutException:
        logger.warning(f"[API] 密钥验证超时: {key_type}")
        return {"valid": False}
    except httpx.ConnectError:
        logger.warning(f"[API] 无法连接到服务: {key_type}")
        return {"valid": False}
    except Exception as e:
        logger.warning(f"[API] 密钥验证失败: {key_type} - {str(e)}")
        return {"valid": False}


@router.post("/settings/reset")
async def reset_settings(payload: ResetSettingsRequest, db: DbDep):
    """
    POST /tasks/settings/reset - 重置配置为工业级默认值

    Args:
        payload: {"target": "ai" | "regex"}

    Returns:
        操作结果
    """
    target = payload.target.strip().lower()

    from app.infra.database.repositories.config_repo import RESET_TARGETS_MAP
    if target not in RESET_TARGETS_MAP:
        valid = ", ".join(RESET_TARGETS_MAP.keys())
        logger.error(f"[API] 重置配置失败: target 必须为 {valid}，收到: {target}")
        return {"success": False, "message": f"target 必须为 {valid}"}

    try:
        db.reset_settings_to_defaults(target)

        logger.info(f"[API] 触发配置重置: {target}")

        return {
            "success": True,
            "message": f"{target.upper()} 配置已重置为工业级默认值"
        }
    except Exception as e:
        logger.error(f"[API] 配置重置失败: {e}")
        return {"success": False, "message": f"重置失败: {str(e)}"}
