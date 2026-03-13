"""
字幕引擎 - 简体优先评分系统

核心特性：
1. 简体优先：zh-CN 优先级最高
2. 评分系统：根据语言、格式、来源评分
3. OpenSubtitles 集成：支持 API 搜索
4. 自动下载：下载最佳匹配字幕
5. 听障字幕过滤：自动剔除带听障特效的字幕
6. 本地字幕检测：避免重复下载
"""
import asyncio
import os
import re
import httpx
from typing import Optional, List, Dict, Literal, Tuple
from pathlib import Path
from datetime import datetime
import logging
from app.infra.constants import VALID_SUB_EXTS

logger = logging.getLogger(__name__)


class SubtitleFatalError(Exception):
    """字幕服务全局致命错误（触发熔断）

    触发条件：
    - 401 Unauthorized：API Key 无效
    - 403 Forbidden：API 额度耗尽或账号被封
    - 429 限流重试 3 次仍失败：API 严重限流
    """


class SubtitleEngine:
    """字幕下载引擎"""
    
    # 语言优先级评分
    LANGUAGE_SCORES = {
        'zh-CN': 100,  # 简体中文
        'zh-cn': 100,
        'zh': 90,      # 中文（未指定）
        'zh-TW': 50,   # 繁体中文
        'zh-tw': 50,
        'zh-HK': 40,   # 香港繁体
        'zh-hk': 40,
        'en': 30,      # 英文
    }
    
    # 格式优先级评分
    FORMAT_SCORES = {
        'srt': 10,
        'ass': 8,
        'ssa': 6,
        'sub': 4,
    }
    
    # 有效字幕扩展名（从全局常量导入，包含 .idx，补充原缺失格式）
    # 注意：直接引用模块级导入的 VALID_SUB_EXTS，不在类内重新赋值以避免名称遮蔽
    _VALID_SUB_EXTS = VALID_SUB_EXTS
    
    def __init__(self, api_key: Optional[str] = None, user_agent: Optional[str] = None):
        """
        初始化字幕引擎
        
        Args:
            api_key: OpenSubtitles API Key
            user_agent: User-Agent 字符串
        """
        self.api_key = api_key
        self.user_agent = user_agent or "SubtitleHunter v13.2"
        self.base_url = "https://api.opensubtitles.com/api/v1"
        logger.info("字幕引擎初始化")
    
    @staticmethod
    def _parse_season_episode_from_path(file_path: str) -> Tuple[Optional[int], Optional[int]]:
        """从路径/文件名解析 S01E05 或 s1e5 等，返回 (season, episode)。"""
        name = Path(file_path).stem.lower()
        m = re.search(r"[s](\d{1,4})\s*[e](\d{1,4})", name, re.I)
        if m:
            return int(m.group(1)), int(m.group(2))
        m = re.search(r"(\d{1,4})\s*x\s*(\d{1,4})", name, re.I)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None, None
    
    @staticmethod
    def _is_hearing_impaired(attrs: dict) -> bool:
        """
        统一判断是否为带听障特效字幕：
        - 优先读取 attributes['hearing_impaired']
        - 回退到 attributes['feature_details']['hearing_impaired']
        """
        hi = attrs.get("hearing_impaired")
        if hi is None:
            feature_details = attrs.get("feature_details") or {}
            hi = feature_details.get("hearing_impaired")
        return bool(hi)

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        params: dict = None,
        json: dict = None,
        base_wait_429: float = 5.0,
    ) -> Optional[httpx.Response]:
        """
        SubtitleEngine 内部 HTTP 重试私有方法

        设计目标：
        - 复用调用方传入的 AsyncClient（保留 TCP 连接池，避免重复 TLS 握手）
        - 数据库回写留在调用方（业务逻辑不侵入工具层）
        - 统一处理 429 限流和 5xx 服务器错误的退避策略

        Args:
            client: 已创建的 httpx.AsyncClient 实例（由调用方在 async with 内传入）
            method: HTTP 方法（"GET" 或 "POST"）
            url: 请求 URL
            params: GET 查询参数
            json: POST JSON 请求体
            base_wait_429: 429 限流首次等待时间（秒），默认 5s；下载时传入 5.0，搜索也是 5.0

        Returns:
            httpx.Response: 成功的响应对象
            None: 重试 3 次后仍失败
        """
        for attempt in range(1, 4):  # 最多重试 3 次
            try:
                resp = await client.request(method, url, params=params, json=json)

                # 限流：OpenSubtitles 免费账号每秒限 1 请求，付费账号每秒限 5 请求
                if resp.status_code == 429:
                    wait_time = base_wait_429 * (2 ** (attempt - 1))  # 5s, 10s, 20s
                    logger.warning(f"[SUBTITLE] API 限流 (429)，第 {attempt} 次重试，等待 {wait_time:.0f}s")
                    await asyncio.sleep(wait_time)
                    continue

                # 服务器暂时不可用：3s/6s/12s 退避后重试
                if resp.status_code in (502, 503, 504):
                    wait_time = 3 * (2 ** (attempt - 1))  # 3s, 6s, 12s
                    logger.warning(f"[SUBTITLE] 服务器错误 ({resp.status_code})，第 {attempt} 次重试，等待 {wait_time:.0f}s")
                    await asyncio.sleep(wait_time)
                    continue

                # 401/403 是永久性失败，直接熔断，不进入重试
                # 官方文档：
                #   401 → 用户名/密码错误（登录端点）
                #   403 → api-key 错误/缺失，或 User-Agent 格式不符（必须如 MyApp v1.2.3）
                if resp.status_code in (401, 403):
                    body = ""
                    try:
                        body = resp.text[:200]
                    except Exception:
                        pass
                    raise SubtitleFatalError(
                        f"API 拒绝访问 ({resp.status_code})，请检查 Api-Key 是否有效、"
                        f"User-Agent 是否符合格式（如 MyApp v1.2.3）。响应: {body}"
                    )
                # 406 → 下载配额耗尽（remaining=-1）或 file_id 无效
                # 官方文档：配额耗尽是全局限制，继续请求无意义，直接熔断
                if resp.status_code == 406:
                    body = ""
                    try:
                        body = resp.text[:300]
                    except Exception:
                        pass
                    if "remaining" in body or "downloaded" in body or "quota" in body.lower():
                        raise SubtitleFatalError(
                            f"下载配额已耗尽 (406)，请等待配额重置（每日 UTC 午夜重置）。响应: {body}"
                        )
                    # file_id 无效：非全局致命错误，让 raise_for_status 处理（单任务失败）
                resp.raise_for_status()  # 其他 4xx/5xx 直接抛出，由 except 捕获
                return resp  # 成功返回响应对象

            except httpx.HTTPStatusError as e:
                # HTTP 协议级错误（如 401 未授权、403 禁止访问）
                # 第 1-2 次：等待后重试；第 3 次：向上抛出，由调用方写回数据库
                if attempt < 3:
                    wait_time = 3 * (2 ** (attempt - 1))
                    logger.warning(f"[SUBTITLE] HTTP 错误 ({e.response.status_code})，第 {attempt} 次重试，等待 {wait_time:.0f}s")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[SUBTITLE] 请求失败（已重试 3 次）: {e}")
                    raise
            except httpx.RequestError as e:
                # 网络层错误（DNS 解析失败、连接超时、连接重置等）
                # 第 1-2 次：等待后重试；第 3 次：向上抛出，由调用方写回数据库
                if attempt < 3:
                    wait_time = 3 * (2 ** (attempt - 1))
                    logger.warning(f"[SUBTITLE] 网络错误，第 {attempt} 次重试，等待 {wait_time:.0f}s: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"[SUBTITLE] 请求失败（已重试 3 次）: {e}")
                    raise

        logger.error("[SUBTITLE] 重试 3 次后仍失败，触发全局熔断")
        raise SubtitleFatalError("API 限流重试耗尽（429 连续 3 次），触发全局熔断")
    
    async def download_subtitle_for_task(
        self,
        db_manager,
        file_path: str,
        tmdb_id: str,
        media_type: str,
        imdb_id: Optional[str] = None,
        season: Optional[int] = None,
        episode: Optional[int] = None,
        target_path: Optional[str] = None,
        archive_id: Optional[int] = None
    ) -> str:
        """
        对单条任务执行字幕搜索与下载，并更新 sub_status / last_sub_check
        
        核心流程：
        1. 本地字幕检测：若目标目录已有字幕，直接跳过
        2. 构建搜索参数：优先使用 IMDb ID，无 ID 时降级为文件名搜索
        3. 调用 OpenSubtitles API：搜索字幕
        4. 听障字幕过滤：剔除带听障特效的字幕
        5. 评分排序：简体中文优先，按语言和格式评分
        6. 下载字幕：下载得分最高的字幕
        7. 命名规范：重命名为 AI 字幕格式（.ai.zh-CN.srt）
        8. 更新数据库：写回字幕状态
        
        搜索策略：
        - 电影：使用 imdb_id 或 tmdb_id
        - 剧集：使用 parent_imdb_id 或 parent_tmdb_id + season + episode
        - 降级：无 ID 时使用文件名（query 参数）
        
        听障字幕过滤：
        - 检测字段：attributes.hearing_impaired
        - 过滤策略：剔除所有 hearing_impaired=true 的字幕
        - 兜底：若仅找到听障字幕，返回 "未找到非听障中文字幕"
        
        评分系统：
        - zh-CN（简体中文）：100 分
        - zh（中文未指定）：90 分
        - zh-TW（繁体中文）：50 分
        - zh-HK（香港繁体）：40 分
        - en（英文）：30 分
        
        重试机制：
        - 429 限流：5s、10s、20s 指数退避
        - 502/503/504 服务器错误：3s、6s、12s 指数退避
        - 最多重试 3 次
        
        Args:
            db_manager: 数据库管理器
            file_path: 原始文件路径
            tmdb_id: TMDB ID
            media_type: "movie" 或 "tv"
            imdb_id: IMDB ID（可选）
            season: 季数（剧集）
            episode: 集数（剧集）
            target_path: 归档后的目标视频路径（如果已归档）
            archive_id: 归档表 ID（如果已归档）
        
        Returns:
            结果描述字符串
        """
        if not self.api_key:
            logger.warning("[SUBTITLE] 未配置 OpenSubtitles API Key，跳过")
            return "未配置 API Key"

        video_path = Path(file_path)
        if not video_path.exists():
            logger.warning(f"[SUBTITLE] 文件不存在: {file_path}")
            return "文件不存在"

        # 落盘目录与视频 stem：若已归档则使用 target_path（媒体库地址），确保字幕写入媒体库不留在下载目录
        if target_path and Path(target_path).parent.exists():
            target_dir = Path(target_path).parent
            video_stem = Path(target_path).stem
        else:
            target_dir = video_path.parent
            video_stem = video_path.stem

        # 下载前截断升级：若目标目录下已存在任何以视频名为前缀的 .srt/.ass 字幕（包含自带或 AI 字幕），直接拦截并视为已抓取
        for f in target_dir.iterdir():
            if not f.is_file():
                continue
            suffix = f.suffix.lower()
            if suffix not in {".srt", ".ass"}:
                continue
            if not f.name.lower().startswith(video_stem.lower()):
                continue
            logger.info(f"[SUBTITLE] 目标路径已存在字幕文件，拦截重复下载: {f.name}")
            if archive_id:
                db_manager.update_archive_sub_status(
                    archive_id,
                    "scraped",
                    last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            return "跳过: 本地已有字幕"

        # 构建搜索参数
        subtitle_lang = db_manager.get_config("subtitle_lang", "zh")

        # 根据语言配置设置搜索语言
        if subtitle_lang == "en":
            search_languages = "en"
        else:
            search_languages = "zh,zh-cn,zh-tw,zh-hk"
        
        search_params = {
            "languages": search_languages,
            "type": "episode" if (media_type or "").lower() == "tv" else "movie",
        }
        
        # 🚀 致命修复：构建搜索参数时，优先使用 ID，如果 ID 为空则使用 query 参数（文件名降级搜索）
        has_valid_id = False
        
        if (media_type or "").lower() == "movie":
            if imdb_id and str(imdb_id).strip():
                search_params["imdb_id"] = str(imdb_id).replace("tt", "").lstrip("0") or "0"
                has_valid_id = True
            elif tmdb_id and str(tmdb_id).strip():
                search_params["tmdb_id"] = str(tmdb_id)
                has_valid_id = True
        else:
            # 剧集类型
            if imdb_id and str(imdb_id).strip():
                search_params["parent_imdb_id"] = str(imdb_id).replace("tt", "").lstrip("0") or "0"
                has_valid_id = True
            if tmdb_id and str(tmdb_id).strip():
                search_params["parent_tmdb_id"] = str(tmdb_id)
                has_valid_id = True
            
            # 解析季集号
            if season is None and episode is None:
                season, episode = self._parse_season_episode_from_path(file_path)
            if season is not None:
                search_params["season_number"] = season
            if episode is not None:
                search_params["episode_number"] = episode
        
        # 🛡️ 防御性兜底：如果没有任何有效 ID，必须带上 query 参数，否则 OpenSubtitles API 会返回 400 Bad Request
        if not has_valid_id:
            logger.warning(f"[SUBTITLE] imdb_id 和 tmdb_id 均为空，降级使用文件名搜索: {video_stem}")
            search_params["query"] = video_stem

        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0, headers=headers) as client:
            # ── 搜索字幕（调用私有重试方法）────────────────────────────────────
            try:
                search_resp = await self._request_with_retry(
                    client, "GET",
                    f"{self.base_url}/subtitles",
                    params=search_params,
                    base_wait_429=5.0,
                )
            except SubtitleFatalError:
                raise  # 透传熔断信号，不吞掉
            except Exception as e:
                logger.error(f"[SUBTITLE] 搜索请求失败: {e}")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return f"API 错误: {e}"

            if not search_resp:
                logger.error("[SUBTITLE] 搜索请求失败（未获取到响应）")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "API 错误: 未获取到响应"
            
            data = search_resp.json().get("data", [])

            if not data:
                logger.info(f"[SUBTITLE] 未找到中文字幕: {file_path}")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="missing",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "未找到中文字幕"

            # 先剔除所有带听障特效的字幕
            filtered_data = []
            for s in data:
                attrs = s.get("attributes", {}) or {}
                if self._is_hearing_impaired(attrs):
                    continue
                filtered_data.append(s)

            if not filtered_data:
                logger.info(f"[SUBTITLE] 仅找到带听障特效字幕，按配置全部丢弃: {file_path}")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="missing",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "未找到非听障中文字幕"

            def score_sub(s):
                attrs = s.get("attributes", {})
                lang = (attrs.get("language") or "").lower()
                sc = 0
                if lang == "zh-cn":
                    sc += 100
                elif lang == "zh":
                    sc += 90
                elif lang == "zh-tw":
                    sc += 50
                elif lang == "zh-hk":
                    sc += 40
                return sc

            # 降序排序，选择得分最高的字幕
            sorted_candidates = sorted(filtered_data, key=score_sub, reverse=True)
            best = sorted_candidates[0]
            attrs = best.get("attributes", {})
            files = attrs.get("files", [])
            if not files:
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="missing",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "字幕文件数据为空"
            
            file_id = files[0].get("file_id")
            # 从 API 返回的文件名中动态提取扩展名
            raw_file_name = (files[0].get("file_name") or "").lower()
            _, ext = os.path.splitext(raw_file_name)
            sub_ext = ext if ext in VALID_SUB_EXTS else ".srt"
            # 规范化：.ssa 统一收束为 .ass
            if sub_ext == ".ssa":
                sub_ext = ".ass"
            
            # 语言代码归一化：区分简繁体，并为 AI 字幕生成专属后缀
            raw_lang = (attrs.get("language") or "zh").lower()
            if subtitle_lang == "en":
                norm_lang = "en"
                # 英文字幕：语言代码紧贴扩展名，符合 Plex/Jellyfin 规范
                target_sub = target_dir / f"{video_stem}.ai.en{sub_ext}"
            elif raw_lang in ("zh", "zh-cn"):
                norm_lang = "zh-CN"
                target_sub = target_dir / f"{video_stem}.ai.{norm_lang}{sub_ext}"
            elif raw_lang in ("zh-tw", "zh-hk"):
                norm_lang = "zh-TW"
                target_sub = target_dir / f"{video_stem}.ai.{norm_lang}{sub_ext}"
            else:
                norm_lang = raw_lang
                target_sub = target_dir / f"{video_stem}.ai.{norm_lang}{sub_ext}"

            # ── 下载字幕（调用私有重试方法）────────────────────────────────────
            try:
                download_resp = await self._request_with_retry(
                    client, "POST",
                    f"{self.base_url}/download",
                    json={"file_id": file_id},
                    base_wait_429=5.0,
                )
            except SubtitleFatalError:
                raise  # 透传熔断信号，不吞掉
            except Exception as e:
                logger.error(f"[SUBTITLE] 下载请求失败: {e}")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return f"下载错误: {e}"

            if not download_resp:
                logger.error("[SUBTITLE] 下载请求失败（未获取到响应）")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "下载错误: 未获取到响应"
            
            download_url = download_resp.json().get("link")
            if not download_url:
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "无法获取下载地址"

            content_resp = await client.get(download_url, timeout=60.0)
            content_resp.raise_for_status()
            target_sub.write_bytes(content_resp.content)
            logger.info(f"[SUBTITLE] 字幕已落盘: {target_sub.name}")

            if archive_id:
                db_manager.update_archive_sub_status(
                    archive_id,
                    sub_status="scraped",
                    last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
            return f"成功: {target_sub.name}"
        
        return "完成"
