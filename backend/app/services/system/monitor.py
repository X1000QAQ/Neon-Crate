"""
系统监控服务 - Monitor Service

功能说明：
1. 磁盘空间监控：实时获取磁盘使用情况
2. CPU 使用率监控：获取系统 CPU 占用
3. 服务心跳检测：检查 Radarr/Sonarr 服务可用性

设计目标：
- 为 AI 提供物理世界的"触觉"
- 支持预警阈值判断（磁盘 < 50GB 标记 CRITICAL）
- 异步心跳检测，不阻塞主流程
- 30 秒 TTL 缓存，避免频繁 I/O 和网络请求
"""
import shutil
import psutil
import httpx
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MonitorService:
    """系统监控服务（带 30 秒 TTL 缓存）"""
    
    def __init__(self, db_manager):
        """
        初始化监控服务
        
        Args:
            db_manager: DatabaseManager 实例，用于读取配置
        """
        self.db = db_manager
        self._cache: Optional[Dict] = None
        self._cache_timestamp: float = 0
        self._cache_ttl: int = 30  # 缓存有效期 30 秒
    
    async def get_system_status(self) -> Dict:
        """
        获取系统完整状态快照（带 30 秒 TTL 缓存）
        
        缓存策略：
        - 缓存命中：立即返回缓存数据（耗时 < 1ms）
        - 缓存过期：执行完整监控（磁盘 I/O + 网络心跳）
        
        包含：
        - 磁盘空间（剩余 GB、使用率、状态）
        - CPU 使用率
        - 服务心跳（Radarr/Sonarr 在线状态）
        
        Returns:
            Dict: 系统状态字典
        """
        # 缓存命中检查
        current_time = time.time()
        if self._cache and (current_time - self._cache_timestamp) < self._cache_ttl:
            logger.debug(f"[MONITOR] 缓存命中，剩余 TTL: {self._cache_ttl - (current_time - self._cache_timestamp):.1f}s")
            return self._cache
        
        # 缓存过期，执行完整监控
        logger.debug("[MONITOR] 缓存过期，执行完整系统监控")
        
        # 1. 磁盘空间监控
        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024**3)
            used_gb = usage.used / (1024**3)
            total_gb = usage.total / (1024**3)
            usage_percent = round((usage.used / usage.total) * 100, 2)
            
            # 预警阈值判断
            if free_gb < 20:
                disk_status = "CRITICAL"
            elif free_gb < 50:
                disk_status = "WARNING"
            else:
                disk_status = "HEALTHY"
        except Exception as e:
            logger.error(f"[MONITOR] 磁盘监控失败: {e}")
            free_gb = 0
            used_gb = 0
            total_gb = 0
            usage_percent = 0
            disk_status = "UNKNOWN"
        
        # 2. CPU 使用率监控
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
        except Exception as e:
            logger.warning(f"[MONITOR] CPU 监控失败: {e}")
            cpu_percent = 0
        
        # 3. 服务心跳检测（异步）
        radarr_status = await self._check_radarr()
        sonarr_status = await self._check_sonarr()
        
        # 构造结果并更新缓存
        result = {
            "disk_free_gb": round(free_gb, 2),
            "disk_used_gb": round(used_gb, 2),
            "disk_total_gb": round(total_gb, 2),
            "disk_usage_percent": usage_percent,
            "disk_status": disk_status,
            "cpu_usage_percent": round(cpu_percent, 2),
            "services": {
                "radarr": radarr_status,
                "sonarr": sonarr_status,
            }
        }
        
        # 更新缓存
        self._cache = result
        self._cache_timestamp = current_time
        logger.debug(f"[MONITOR] 缓存已更新，TTL: {self._cache_ttl}s")
        
        return result
    
    async def _check_radarr(self) -> str:
        """
        Radarr 服务心跳检测
        
        通过请求 /api/v3/system/status 接口判断服务是否可用
        
        Returns:
            str: "ONLINE" / "OFFLINE" / "NOT_CONFIGURED"
        """
        url = self.db.get_config("radarr_url", "").strip()
        key = self.db.get_config("radarr_api_key", "").strip()
        
        if not url or not key:
            return "NOT_CONFIGURED"
        
        try:
            url = url.rstrip('/')
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{url}/api/v3/system/status",
                    headers={"X-Api-Key": key}
                )
                if resp.status_code == 200:
                    logger.debug("[MONITOR] Radarr 心跳检测成功")
                    return "ONLINE"
                else:
                    logger.warning(f"[MONITOR] Radarr 返回异常状态码: {resp.status_code}")
                    return "OFFLINE"
        except httpx.TimeoutException:
            logger.warning("[MONITOR] Radarr 心跳检测超时")
            return "OFFLINE"
        except Exception as e:
            logger.warning(f"[MONITOR] Radarr 心跳检测失败: {e}")
            return "OFFLINE"
    
    async def _check_sonarr(self) -> str:
        """
        Sonarr 服务心跳检测
        
        通过请求 /api/v3/system/status 接口判断服务是否可用
        
        Returns:
            str: "ONLINE" / "OFFLINE" / "NOT_CONFIGURED"
        """
        url = self.db.get_config("sonarr_url", "").strip()
        key = self.db.get_config("sonarr_api_key", "").strip()
        
        if not url or not key:
            return "NOT_CONFIGURED"
        
        try:
            url = url.rstrip('/')
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    f"{url}/api/v3/system/status",
                    headers={"X-Api-Key": key}
                )
                if resp.status_code == 200:
                    logger.debug("[MONITOR] Sonarr 心跳检测成功")
                    return "ONLINE"
                else:
                    logger.warning(f"[MONITOR] Sonarr 返回异常状态码: {resp.status_code}")
                    return "OFFLINE"
        except httpx.TimeoutException:
            logger.warning("[MONITOR] Sonarr 心跳检测超时")
            return "OFFLINE"
        except Exception as e:
            logger.warning(f"[MONITOR] Sonarr 心跳检测失败: {e}")
            return "OFFLINE"
    
    def get_disk_summary(self) -> str:
        """
        获取磁盘状态摘要（同步方法，用于快速查询）
        
        Returns:
            str: 磁盘状态摘要文本
        """
        try:
            usage = shutil.disk_usage("/")
            free_gb = usage.free / (1024**3)
            usage_percent = round((usage.used / usage.total) * 100, 2)
            
            if free_gb < 20:
                status = "⚠️ CRITICAL"
            elif free_gb < 50:
                status = "⚠️ WARNING"
            else:
                status = "✅ HEALTHY"
            
            return f"磁盘: {free_gb:.1f}GB 可用 ({usage_percent}% 已用) - {status}"
        except Exception as e:
            logger.error(f"[MONITOR] 磁盘摘要获取失败: {e}")
            return "磁盘: 状态未知"
