"""
Servarr 核心通信组件 - V11 "寻猎者"计划 (V9.3 AI 原生版)

功能：
1. 与 Radarr 对接实现电影自动下载
2. 与 Sonarr 对接实现剧集自动下载
3. TMDB 侦察兵：基于 TMDB ID 的精准匹配
4. 物理映射信任：tmdb:ID 搜索结果 100% 可信，无需人工校验
5. 完整的 API 调用链路（TMDB Recon -> Lookup -> RootFolder -> QualityProfile -> Add）

技术特性：
- 异步 HTTP 通信（httpx）
- 配置动态读取（从 db_manager）
- TMDB 预侦察 + 物理 ID 映射
- 工业级错误处理与日志记录
"""
import httpx
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class ServarrClient:
    """Servarr 通信客户端 - 统一管理 Radarr 和 Sonarr 下载请求"""
    
    def __init__(self, db_manager):
        """
        初始化 Servarr 客户端
        
        Args:
            db_manager: DatabaseManager 实例，用于读取配置
        """
        self.db = db_manager
        logger.info("[Servarr] 寻猎者引擎已启动 (V9.3 AI原生版)")
    
    def _tmdb_recon(self, name: str, media_type: str, year: str = "") -> Optional[Dict]:
        """
        TMDB 侦察兵 - 预先获取真实的 TMDB 数据
        
        设计目标：
        - 在调用 Radarr/Sonarr 之前，先从 TMDB 获取准确的 ID
        - 避免 Radarr/Sonarr 搜索结果不准确的问题
        - 提供物理映射信任：tmdb:ID 搜索结果 100% 可信
        
        工作流程：
        1. 调用 TMDB API 搜索影片
        2. 若提供年份，优先选择年份匹配的结果
        3. 返回 TMDB ID、标题、年份
        
        为什么需要侦察兵？
        - Radarr/Sonarr 的搜索结果可能不准确
        - 直接使用 TMDB ID 搜索（tmdb:123）可以精准匹配
        - 避免用户选择错误的影片
        
        Args:
            name: 片名
            media_type: 媒体类型 (movie/tv)
            year: 年份（可选）
            
        Returns:
            Optional[Dict]: {"tmdbId": int, "title": str, "year": str} 或 None
        """
        try:
            # 获取 TMDB API Key
            tmdb_api_key = self.db.get_config("tmdb_api_key", "").strip()
            if not tmdb_api_key:
                logger.error("[TMDB-Recon] 未配置 TMDB API Key，无法执行侦察")
                return None
            
            # 导入 TMDB 适配器
            from app.services.metadata.adapters import TMDBAdapter
            tmdb = TMDBAdapter(tmdb_api_key)
            
            # 根据类型调用对应的搜索方法
            if media_type == "tv":
                results = tmdb.search_tv(name, year if year else None)
            else:
                results = tmdb.search_movie(name, year if year else None)
            
            if not results or len(results) == 0:
                logger.warning(f"[TMDB-Recon] 未找到匹配结果: {name} ({media_type})")
                return None
            
            # 若提供了年份，优先选择年份匹配的结果，否则取第一个
            first = results[0]
            if year:
                for r in results:
                    rd = r.get("release_date") or r.get("first_air_date") or ""
                    if rd.startswith(str(year)):
                        first = r
                        logger.info(f"[TMDB-Recon] 年份匹配命中: {r.get('title') or r.get('name')} ({rd[:4]})")
                        break
            tmdb_id = first.get("id")
            title = first.get("title") if media_type == "movie" else first.get("name")
            result_year = ""
            
            if media_type == "movie":
                release_date = first.get("release_date", "")
                if release_date and len(release_date) >= 4:
                    result_year = release_date[:4]
            else:
                first_air_date = first.get("first_air_date", "")
                if first_air_date and len(first_air_date) >= 4:
                    result_year = first_air_date[:4]
            
            logger.info(f"[TMDB-Recon] 侦察成功 -> TMDB ID: {tmdb_id}, 标题: {title}, 年份: {result_year}")
            
            return {
                "tmdbId": tmdb_id,
                "title": title,
                "year": result_year
            }
            
        except Exception as e:
            logger.error(f"[TMDB-Recon] 侦察异常: {str(e)}")
            return None
    
    async def check_existence(self, tmdb_id: int, media_type: str = "movie") -> Dict:
        """
        查重审计：通过 TMDB ID 检查资源是否已存在于 Radarr/Sonarr 库中

        Radarr: GET /api/v3/movie/lookup?term=tmdb:{tmdb_id}
        Sonarr: GET /api/v3/series/lookup?term=tmdb:{tmdb_id}

        判定规则：lookup 返回列表的首项 id > 0 视为库内已存在。

        Args:
            tmdb_id:    TMDB ID
            media_type: "movie" | "tv"

        Returns:
            Dict: {"exists": bool, "status": Optional[str]}
                  status 取值："已在库中"、"正在监控（文件缺失）"、None
        """
        if not tmdb_id:
            return {"exists": False, "status": None}

        try:
            if media_type == "tv":
                base_url = self.db.get_config("sonarr_url", "").strip().rstrip("/")
                api_key  = self.db.get_config("sonarr_api_key", "").strip()
                if not base_url or not api_key:
                    return {"exists": False, "status": None}
                lookup_url = f"{base_url}/api/v3/series/lookup"
                headers    = {"X-Api-Key": api_key}
            else:
                base_url = self.db.get_config("radarr_url", "").strip().rstrip("/")
                api_key  = self.db.get_config("radarr_api_key", "").strip()
                if not base_url or not api_key:
                    return {"exists": False, "status": None}
                lookup_url = f"{base_url}/api/v3/movie/lookup"
                headers    = {"X-Api-Key": api_key}

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    lookup_url,
                    headers=headers,
                    params={"term": f"tmdb:{tmdb_id}"},
                )
                resp.raise_for_status()
                items = resp.json()

            if not items:
                return {"exists": False, "status": None}

            first = items[0]
            item_id = first.get("id", 0)
            logger.info(f"[{'Radarr' if media_type == 'movie' else 'Sonarr'}] 查重审计: tmdb:{tmdb_id} -> 库内 ID: {item_id}")

            if item_id and item_id > 0:
                has_file = first.get("hasFile", False) or first.get("statistics", {}).get("episodeFileCount", 0) > 0
                status = "已在库中" if has_file else "正在监控（文件缺失）"
                return {"exists": True, "status": status}

            return {"exists": False, "status": None}

        except Exception as e:
            logger.warning(f"[Servarr] 查重审计异常（非阻断）: {e}")
            return {"exists": False, "status": None}

    async def add_movie(self, title: str, year: str = "", tmdb_id: int = 0) -> Dict:
        """
        对接 Radarr 添加电影下载任务 (V9.3 AI 原生版)
        
        完整流程（5 步走）：
        
        步骤 0：TMDB 侦察兵
        - 若提供 tmdb_id，直接使用（候选列表场景）
        - 否则调用 TMDB API 搜索，获取准确的 TMDB ID
        
        步骤 A：Lookup（精准搜索）
        - 使用 tmdb:ID 格式搜索 Radarr
        - 物理映射信任：搜索结果 100% 可信，无需人工校验
        
        步骤 B：Root Folder（获取根目录）
        - 获取 Radarr 配置的根目录
        - 电影将下载到此目录
        
        步骤 C：Quality Profile（获取质量配置）
        - 获取 Radarr 配置的质量档案
        - 决定下载的视频质量（1080p、4K 等）
        
        步骤 D：查重防御
        - 检查电影是否已在 Radarr 库中
        - 若已存在，触发搜索补全命令（N8N 核心逻辑）
        
        步骤 E：Add（添加到下载队列）
        - 将电影添加到 Radarr
        - 自动触发搜索和下载
        
        步骤 F：兜底拦截
        - 捕获 400 错误中的 "already been added" 消息
        - 防止遗漏已存在的电影
        
        Args:
            title: 电影名称
            year: 年份（可选）
            tmdb_id: TMDB ID（可选，提供时跳过 TMDB 侦察，直接使用）
            
        Returns:
            Dict: {"success": bool, "msg": str, "data": dict}
        """
        # 步骤 0: TMDB 侦察兵 - 预先获取真实数据（有 tmdb_id 时跳过）
        if tmdb_id:
            tmdb_info = {"tmdbId": tmdb_id, "title": title, "year": year}
            logger.info(f"[Radarr] 使用候选 TMDB ID 直接下载: {tmdb_id} - {title}")
        else:
            logger.info(f"[Radarr] 启动 TMDB 侦察兵: {title}")
            tmdb_info = self._tmdb_recon(title, "movie", year)
        
        if not tmdb_info:
            return {
                "success": False, 
                "msg": f"TMDB 侦察失败，未找到「{title}」的匹配数据", 
                "data": {}
            }
        
        # 1. 读取 Radarr 配置
        radarr_url = self.db.get_config("radarr_url", "").strip()
        radarr_api_key = self.db.get_config("radarr_api_key", "").strip()
        quality_profile_name = self.db.get_config("radarr_quality_profile", "Any").strip()
        
        if not radarr_url or not radarr_api_key:
            logger.warning("[Radarr] 未配置 Radarr URL 或 API Key")
            return {"success": False, "msg": "未配置 Radarr，请前往设置页面完成配置", "data": {}}
        
        # 确保 URL 不以斜杠结尾
        radarr_url = radarr_url.rstrip('/')
        
        # 构造请求头
        headers = {"X-Api-Key": radarr_api_key}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 步骤 A: Lookup - 使用 TMDB ID 精准搜索
                search_term = f"tmdb:{tmdb_info['tmdbId']}"
                logger.info(f"[Radarr] 精准搜索 (TMDB ID): {search_term}")
                
                lookup_url = f"{radarr_url}/api/v3/movie/lookup"
                lookup_resp = await client.get(
                    lookup_url,
                    headers=headers,
                    params={"term": search_term}
                )
                lookup_resp.raise_for_status()
                lookup_results = lookup_resp.json()
                
                if not lookup_results or len(lookup_results) == 0:
                    logger.warning(f"[Radarr] Radarr 中未找到 TMDB ID {tmdb_info['tmdbId']}")
                    return {"success": False, "msg": f"Radarr 中未找到「{title}」", "data": {}}
                
                # 取第一个匹配结果（物理映射信任：tmdb:ID 搜索结果 100% 可信）
                movie_data = lookup_results[0]
                radarr_title = movie_data.get('title', 'Unknown')
                
                logger.info(f"[Radarr] 物理映射确认: {radarr_title} ({movie_data.get('year', 'N/A')}) - TMDB ID: {tmdb_info['tmdbId']}")
                
                # 步骤 B: Root Folder - 获取根目录
                rootfolder_url = f"{radarr_url}/api/v3/rootfolder"
                rootfolder_resp = await client.get(rootfolder_url, headers=headers)
                rootfolder_resp.raise_for_status()
                rootfolders = rootfolder_resp.json()
                
                if not rootfolders or len(rootfolders) == 0:
                    logger.error("[Radarr] 未配置根目录")
                    return {"success": False, "msg": "Radarr 未配置根目录，请在 Radarr 中添加根目录", "data": {}}
                
                root_path = rootfolders[0]["path"]
                logger.info(f"[Radarr] 使用根目录: {root_path}")
                
                # 步骤 C: Quality Profile - 获取质量配置
                profile_url = f"{radarr_url}/api/v3/qualityprofile"
                profile_resp = await client.get(profile_url, headers=headers)
                profile_resp.raise_for_status()
                profiles = profile_resp.json()
                
                if not profiles or len(profiles) == 0:
                    logger.error("[Radarr] 未找到质量配置")
                    return {"success": False, "msg": "Radarr 未配置质量档案", "data": {}}
                
                # 尝试匹配配置中的质量档案名称，否则使用第一个
                profile_id = profiles[0]["id"]
                for profile in profiles:
                    if profile["name"].lower() == quality_profile_name.lower():
                        profile_id = profile["id"]
                        break
                
                logger.info(f"[Radarr] 使用质量档案 ID: {profile_id}")
                
                # 步骤 D: 查重防御 - 检查是否已在库中（N8N V9.2 对齐）
                # 如果 lookup 返回的数据中 id > 0，说明已存在于 Radarr 库中
                if movie_data.get("id") and movie_data["id"] > 0:
                    existing_id = movie_data["id"]
                    logger.info(f"[Radarr] 电影已存在 (ID: {existing_id}): {radarr_title}")
                    
                    # 触发自动搜索补全（N8N 核心逻辑）
                    command_payload = {
                        "name": "MoviesSearch",
                        "movieIds": [existing_id]
                    }
                    command_url = f"{radarr_url}/api/v3/command"
                    await client.post(command_url, headers=headers, json=command_payload)
                    
                    logger.info(f"[Radarr] 已触发搜索补全命令 (ID: {existing_id})")
                    
                    return {
                        "success": True,
                        "msg": f"[OK] {radarr_title} 已在库中，已触发搜索补全。",
                        "data": {"status": "exists", "id": existing_id, "title": radarr_title}
                    }
                
                # 步骤 E: Add - 添加电影到下载队列
                movie_data["rootFolderPath"] = root_path
                movie_data["qualityProfileId"] = profile_id
                movie_data["monitored"] = True
                movie_data["addOptions"] = {"searchForMovie": True}
                
                add_url = f"{radarr_url}/api/v3/movie"
                add_resp = await client.post(add_url, headers=headers, json=movie_data)
                add_resp.raise_for_status()
                result = add_resp.json()
                
                movie_title = result.get("title", title)
                logger.info(f"[Radarr] 成功添加电影: {movie_title}")
                
                return {
                    "success": True,
                    "msg": "成功添加到 Radarr 下载队列",
                    "data": {"title": movie_title, "year": result.get("year", "")}
                }
                
        except httpx.HTTPStatusError as e:
            # 步骤 F: 兜底拦截（防止遗漏）
            if e.response.status_code == 400:
                try:
                    error_data = e.response.json()
                    error_msg = str(error_data)
                    if "already been added" in error_msg.lower():
                        logger.info(f"[Radarr] 电影已存在（兜底拦截）: {title}")
                        return {
                            "success": True, 
                            "msg": f"{title} 已在监控队列中，已触发补全搜索。", 
                            "data": {"status": "exists"}
                        }
                except Exception as parse_err:
                    logger.error(f"[Radarr] 400 错误响应解析失败: {parse_err} | 原始数据: {e.response.text}")
                    return {"success": False, "msg": f"添加失败，Radarr 拒绝了请求: {e.response.status_code}", "data": {}}
            
            error_msg = f"HTTP 错误 {e.response.status_code}: {e.response.text}"
            logger.error(f"[Radarr] {error_msg}")
            return {"success": False, "msg": f"Radarr 请求失败: {error_msg}", "data": {}}
        except Exception as e:
            logger.error(f"[Radarr] 未知错误: {str(e)}")
            return {"success": False, "msg": f"Radarr 通信异常: {str(e)}", "data": {}}
    
    async def add_series(self, title: str, year: str = "", tmdb_id: int = 0) -> Dict:
        """
        对接 Sonarr 添加剧集下载任务 (V9.3 AI 原生版)
        
        完整流程（5 步走）：
        
        步骤 0：TMDB 侦察兵
        - 若提供 tmdb_id，直接使用（候选列表场景）
        - 否则调用 TMDB API 搜索，获取准确的 TMDB ID
        
        步骤 A：Lookup（精准搜索）
        - 使用 tmdb:ID 格式搜索 Sonarr
        - 物理映射信任：搜索结果 100% 可信，无需人工校验
        
        步骤 B：Root Folder（获取根目录）
        - 获取 Sonarr 配置的根目录
        - 剧集将下载到此目录
        
        步骤 C：Quality Profile（获取质量配置）
        - 获取 Sonarr 配置的质量档案
        - 决定下载的视频质量（1080p、4K 等）
        
        步骤 D：Add（添加到下载队列）
        - 将剧集添加到 Sonarr
        - 自动触发搜索和下载
        - 监控所有季和集
        
        步骤 E：已存在拦截
        - 捕获 400 错误中的 "already been added" 消息
        - 防止重复添加
        
        Args:
            title: 剧集名称
            year: 年份（可选）
            tmdb_id: TMDB ID（可选，提供时跳过 TMDB 侦察，直接使用）
            
        Returns:
            Dict: {"success": bool, "msg": str, "data": dict}
        """
        # 步骤 0: TMDB 侦察兵 - 预先获取真实数据（有 tmdb_id 时跳过）
        if tmdb_id:
            tmdb_info = {"tmdbId": tmdb_id, "title": title, "year": year}
            logger.info(f"[Sonarr] 使用候选 TMDB ID 直接下载: {tmdb_id} - {title}")
        else:
            logger.info(f"[Sonarr] 启动 TMDB 侦察兵: {title}")
            tmdb_info = self._tmdb_recon(title, "tv", year)
        
        if not tmdb_info:
            return {
                "success": False, 
                "msg": f"TMDB 侦察失败，未找到「{title}」的匹配数据", 
                "data": {}
            }
        
        # 1. 读取 Sonarr 配置
        sonarr_url = self.db.get_config("sonarr_url", "").strip()
        sonarr_api_key = self.db.get_config("sonarr_api_key", "").strip()
        quality_profile_name = self.db.get_config("sonarr_quality_profile", "Any").strip()
        
        if not sonarr_url or not sonarr_api_key:
            logger.warning("[Sonarr] 未配置 Sonarr URL 或 API Key")
            return {"success": False, "msg": "未配置 Sonarr，请前往设置页面完成配置", "data": {}}
        
        # 确保 URL 不以斜杠结尾
        sonarr_url = sonarr_url.rstrip('/')
        
        # 构造请求头
        headers = {"X-Api-Key": sonarr_api_key}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # 步骤 A: Lookup - 使用 TMDB ID 精准搜索
                search_term = f"tmdb:{tmdb_info['tmdbId']}"
                logger.info(f"[Sonarr] 精准搜索 (TMDB ID): {search_term}")
                
                lookup_url = f"{sonarr_url}/api/v3/series/lookup"
                lookup_resp = await client.get(
                    lookup_url,
                    headers=headers,
                    params={"term": search_term}
                )
                lookup_resp.raise_for_status()
                lookup_results = lookup_resp.json()
                
                if not lookup_results or len(lookup_results) == 0:
                    logger.warning(f"[Sonarr] Sonarr 中未找到 TMDB ID {tmdb_info['tmdbId']}")
                    return {"success": False, "msg": f"Sonarr 中未找到「{title}」", "data": {}}
                
                # 取第一个匹配结果（物理映射信任：tmdb:ID 搜索结果 100% 可信）
                series_data = lookup_results[0]
                sonarr_title = series_data.get('title', 'Unknown')
                
                logger.info(f"[Sonarr] 物理映射确认: {sonarr_title} ({series_data.get('year', 'N/A')}) - TMDB ID: {tmdb_info['tmdbId']}")
                
                # 步骤 B: Root Folder - 获取根目录
                rootfolder_url = f"{sonarr_url}/api/v3/rootfolder"
                rootfolder_resp = await client.get(rootfolder_url, headers=headers)
                rootfolder_resp.raise_for_status()
                rootfolders = rootfolder_resp.json()
                
                if not rootfolders or len(rootfolders) == 0:
                    logger.error("[Sonarr] 未配置根目录")
                    return {"success": False, "msg": "Sonarr 未配置根目录，请在 Sonarr 中添加根目录", "data": {}}
                
                root_path = rootfolders[0]["path"]
                logger.info(f"[Sonarr] 使用根目录: {root_path}")
                
                # 步骤 C: Quality Profile - 获取质量配置
                profile_url = f"{sonarr_url}/api/v3/qualityprofile"
                profile_resp = await client.get(profile_url, headers=headers)
                profile_resp.raise_for_status()
                profiles = profile_resp.json()
                
                if not profiles or len(profiles) == 0:
                    logger.error("[Sonarr] 未找到质量配置")
                    return {"success": False, "msg": "Sonarr 未配置质量档案", "data": {}}
                
                # 尝试匹配配置中的质量档案名称，否则使用第一个
                profile_id = profiles[0]["id"]
                for profile in profiles:
                    if profile["name"].lower() == quality_profile_name.lower():
                        profile_id = profile["id"]
                        break
                
                logger.info(f"[Sonarr] 使用质量档案 ID: {profile_id}")
                
                # 步骤 D: Add - 添加剧集到下载队列
                series_data["rootFolderPath"] = root_path
                series_data["qualityProfileId"] = profile_id
                series_data["monitored"] = True
                series_data["addOptions"] = {"searchForMissingEpisodes": True}
                
                add_url = f"{sonarr_url}/api/v3/series"
                add_resp = await client.post(add_url, headers=headers, json=series_data)
                add_resp.raise_for_status()
                result = add_resp.json()
                
                series_title = result.get("title", title)
                logger.info(f"[Sonarr] 成功添加剧集: {series_title}")
                
                return {
                    "success": True,
                    "msg": "成功添加到 Sonarr 下载队列",
                    "data": {"title": series_title, "year": result.get("year", "")}
                }
                
        except httpx.HTTPStatusError as e:
            # 步骤 E: 已存在拦截
            if e.response.status_code == 400:
                try:
                    error_data = e.response.json()
                    error_msg = str(error_data)
                    if "already been added" in error_msg.lower():
                        logger.info(f"[Sonarr] 剧集已存在: {title}")
                        return {
                            "success": True, 
                            "msg": f"{title} 已在监控队列中，已触发补全搜索。", 
                            "data": {"status": "exists"}
                        }
                except Exception as parse_err:
                    logger.error(f"[Sonarr] 400 错误响应解析失败: {parse_err} | 原始数据: {e.response.text}")
                    return {"success": False, "msg": f"添加失败，Sonarr 拒绝了请求: {e.response.status_code}", "data": {}}
            
            error_msg = f"HTTP 错误 {e.response.status_code}: {e.response.text}"
            logger.error(f"[Sonarr] {error_msg}")
            return {"success": False, "msg": f"Sonarr 请求失败: {error_msg}", "data": {}}
        except Exception as e:
            logger.error(f"[Sonarr] 未知错误: {str(e)}")
            return {"success": False, "msg": f"Sonarr 通信异常: {str(e)}", "data": {}}
