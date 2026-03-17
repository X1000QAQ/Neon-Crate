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
    获取完整系统配置（settings + paths）。

    业务链路：
    从配置仓储读取 `config.json/secure_keys.json` → 组合为 SettingsConfig 返回 → 前端按 UI 规则对敏感值做展示遮罩。

    Args:
        db: 数据库依赖注入（DbDep），提供 `get_all_config()` 读取能力。

    Returns:
        SettingsConfig: 完整配置对象，包含：
            - settings: 系统设置（含各类 API Key、偏好与策略）
            - paths: 路径配置（download/library 等）

    Raises:
        HTTPException:
            - 500: 配置读取失败（I/O 或 JSON 损坏等异常链路）。
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
    更新系统配置并持久化（写入 config.json/secure_keys.json）。

    业务链路：
    接收 SettingsConfig → 前置校验（启用的媒体库配置必须满足约束）→ 持久化落盘 →
    触发仪表盘媒体库数量缓存更新（避免配置变更后大屏显示为 0）。

    Args:
        config: SettingsConfig，请求体包含 `settings` 与 `paths`。
        db: 数据库依赖注入（DbDep），提供 `save_all_config()` 写盘能力。

    Returns:
        Dict[str, Any]:
            - success: 是否成功
            - message: 人类可读提示

    Raises:
        HTTPException:
            - 400: 配置校验失败（媒体库数量/类型约束不满足）。
            - 500: 写盘失败或运行时异常。
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
    验证第三方 API 密钥有效性（不回显密钥本身）。

    业务链路：
    根据 key_type 选择验证策略 → 发起最小化探测请求（或格式校验）→ 返回 `{valid: bool}`。

    Body:
        payload: dict，关键字段：
            - key_type: 密钥类型（tmdb_api_key/sonarr_api_key/radarr_api_key/os_api_key）
            - key_value: 密钥值
            - url: 可选，Sonarr/Radarr 服务地址（未提供则尝试从配置读取）

    Returns:
        Dict[str, bool]:
            - valid: 是否有效

    Raises:
        HTTPException:
            - 400: 缺少 key_type/key_value 等必要字段。
            - 500: 运行时异常（理论上函数内部尽量吞并并返回 valid=false，但仍可能有极端异常）。
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
    重置指定配置分区为工业级默认值（仅重置白名单字段）。

    业务链路：
    校验 target（ai/regex/formats...）→ 读取重置映射表 → 对该分区字段执行默认值覆盖 → 返回结果。

    Args:
        payload: ResetSettingsRequest，请求体包含 `target`（如 ai/regex）。
        db: 数据库依赖注入（DbDep）。

    Returns:
        Dict[str, Any]: 操作结果，包含 success/message。

    Raises:
        HTTPException:
            - 400: target 不在允许范围（映射表不支持）。
            - 500: 写盘失败或运行时异常。
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
