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
import re
import httpx
from typing import Optional, List, Dict, Literal, Tuple
from pathlib import Path
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


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
    
    # 有效字幕扩展名
    VALID_SUB_EXTS = {".srt", ".ass", ".vtt", ".ssa", ".sub"}
    
    def __init__(self, api_key: Optional[str] = None, user_agent: Optional[str] = None):
        """
        初始化字幕引擎
        
        Args:
            api_key: OpenSubtitles API Key
            user_agent: User-Agent 字符串
        """
        self.api_key = api_key
        self.user_agent = user_agent or "SubtitleHunter/13.2"
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
        对单条任务执行字幕搜索与下载，并更新 sub_status / last_sub_check。
        
        Args:
            db_manager: 数据库管理器
            file_path: 原始文件路径
            tmdb_id: TMDB ID
            media_type: "movie" 或 "tv"
            imdb_id: IMDB ID（可选）
            season: 季数（剧集）
            episode: 集数（剧集）
            target_path: 归档后的目标视频路径（如果已归档）
        
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
        search_params = {
            "languages": "zh,zh-cn,zh-tw,zh-hk",
            "type": "episode" if (media_type or "").lower() == "tv" else "movie",
        }
        
        if (media_type or "").lower() == "movie":
            if imdb_id:
                search_params["imdb_id"] = str(imdb_id).replace("tt", "").lstrip("0") or "0"
            else:
                search_params["tmdb_id"] = str(tmdb_id or "")
        else:
            if imdb_id:
                search_params["parent_imdb_id"] = str(imdb_id).replace("tt", "").lstrip("0") or "0"
            search_params["parent_tmdb_id"] = str(tmdb_id or "")
            if season is None and episode is None:
                season, episode = self._parse_season_episode_from_path(file_path)
            if season is not None:
                search_params["season_number"] = season
            if episode is not None:
                search_params["episode_number"] = episode

        headers = {
            "Api-Key": self.api_key,
            "User-Agent": self.user_agent,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            try:
                search_resp = await client.get(f"{self.base_url}/subtitles", headers=headers, params=search_params)
                if search_resp.status_code == 429:
                    logger.warning("[SUBTITLE] API 限流，冷却 15 秒")
                    await asyncio.sleep(15)
                    search_resp = await client.get(f"{self.base_url}/subtitles", headers=headers, params=search_params)
                search_resp.raise_for_status()
                data = search_resp.json().get("data", [])
            except Exception as e:
                logger.error(f"[SUBTITLE] 搜索请求失败: {e}")
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return f"API 错误: {e}"

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
            
            # 语言代码归一化：区分简繁体，并为 AI 字幕生成专属后缀
            raw_lang = (attrs.get("language") or "zh").lower()
            if raw_lang in ("zh", "zh-cn"):
                norm_lang = "zh-CN"
            elif raw_lang in ("zh-tw", "zh-hk"):
                norm_lang = "zh-TW"
            else:
                norm_lang = raw_lang

            download_resp = await client.post(f"{self.base_url}/download", headers=headers, json={"file_id": file_id})
            if download_resp.status_code == 429:
                await asyncio.sleep(15)
                download_resp = await client.post(f"{self.base_url}/download", headers=headers, json={"file_id": file_id})
            download_resp.raise_for_status()
            download_url = download_resp.json().get("link")
            if not download_url:
                if archive_id:
                    db_manager.update_archive_sub_status(
                        archive_id,
                        sub_status="failed",
                        last_check=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                return "无法获取下载地址"

            # AI 字幕专属钢印：{video_stem}.ai.{lang_code}.srt，例如 movie.ai.zh-CN.srt
            target_sub = target_dir / f"{video_stem}.ai.{norm_lang}.srt"
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
