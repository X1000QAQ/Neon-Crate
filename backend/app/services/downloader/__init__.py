"""
下载器模块 - Radarr/Sonarr 集成

功能：
1. 与 Radarr 对接实现电影自动下载
2. 与 Sonarr 对接实现剧集自动下载
3. 智能配置读取与错误处理
4. 完整的 API 调用链路（Lookup -> RootFolder -> QualityProfile -> Add）
"""

from .servarr import ServarrClient

__all__ = ["ServarrClient"]
