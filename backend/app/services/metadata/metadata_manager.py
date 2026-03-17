"""
元数据补给站 - MetadataManager

核心功能：
1. NFO 生成：根据 TMDB 数据生成符合 Jellyfin/Emby/Plex 标准的 XML 格式元数据
2. 图片下载：下载 TMDB 海报并保存为作品目录下的 poster.jpg
3. 智能缓存：避免重复下载，提升性能
4. 路径防穿越：所有写入路径均使用 Path.resolve() 校验
5. 网络容错：httpx 替代 requests，支持超时和重试
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from xml.etree import ElementTree as ET
from app.infra.http_utils import http_get_with_retry as _http_get_with_retry

logger = logging.getLogger(__name__)


def _safe_get(data: Any, *keys, default="") -> Any:
    """
    极其严谨的链式 .get() 工具函数，杜绝 KeyError / TypeError

    用法：_safe_get(detail, "credits", "cast", default=[])
    """
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list) and isinstance(key, int):
            current = current[key] if 0 <= key < len(current) else None
        else:
            return default
        if current is None:
            return default
    return current if current is not None else default


def _validate_path(target_path: str, allowed_base: str) -> Path:
    """
    路径防穿越校验（Docker 软链兼容版）

    🚨 架构师警告 (DO NOT MODIFY): 核安全边界，改动极易引发死锁或路径穿越。
    - 这是元数据写盘链路的“路径核安全边界”，被 `generate_nfo/download_poster/download_fanart` 直接调用。
    - 该逻辑需要同时覆盖：
      1) 严格模式：`Path.resolve()` 解析多层软链（含 Unraid `/mnt/user/...` 等场景）
      2) 降级模式：在 Docker/挂载软链无法严格相对化时，使用“带路径边界”的前缀校验兜底
    - 修改不当会导致两类灾难：误杀合法挂载路径（功能瘫痪）或放行路径穿越（安全事故）。

    策略：
    1. 优先使用 Path.resolve() 严格校验（解析软链）
    2. 如果失败，降级为绝对路径字符串前缀校验（兼容 Docker 挂载）
    3. 彻底杜绝 ../ 路径穿越攻击

    Raises:
        ValueError: 路径穿越时抛出
    """
    # ── 第一步：尝试严格软链解析校验 ──────────────────────────
    resolved_target = Path(target_path).resolve()
    resolved_base = Path(allowed_base).resolve()
    try:
        resolved_target.relative_to(resolved_base)
        logger.debug(f"[SECURITY] 路径校验通过（严格模式）: {resolved_target}")
        return resolved_target
    except ValueError:
        # ── 第二步：降级校验（Docker 挂载软链场景）────────────────
        # 使用绝对路径字符串前缀匹配，不解析软链
        abs_target = os.path.abspath(target_path)
        abs_base = os.path.abspath(allowed_base)
        
        # 规范化路径分隔符（Windows/Linux 兼容）
        abs_target_norm = abs_target.replace("\\", "/")
        abs_base_norm = abs_base.replace("\\", "/")
        
        # 注意：必须做“路径边界”校验，避免 /base 与 /base2 的前缀碰撞误放行
        base = abs_base_norm.rstrip("/")
        target = abs_target_norm
        if target == base or target.startswith(base + "/"):
            logger.warning(
                f"[SECURITY] 路径校验通过（降级模式，Docker 软链场景）: "
                f"target={abs_target}, base={abs_base}"
            )
            return Path(abs_target)
        
        # ── 第三步：真正的路径穿越攻击，拦截 ────────────────────
        raise ValueError(
            f"[SECURITY] 路径穿越攻击拦截！"
            f"目标路径 '{abs_target}' 不在允许目录 '{abs_base}' 内。"
            f"resolved_target={resolved_target}, resolved_base={resolved_base}"
        )


# ============================================================
# 空结果对象 - 核心数据缺失时的规范化返回值
# ============================================================
EMPTY_DETAIL: Dict[str, Any] = {
    "id": "",
    "title": "",
    "name": "",
    "original_title": "",
    "original_name": "",
    "overview": "",
    "tagline": "",
    "runtime": 0,
    "vote_average": 0,
    "vote_count": 0,
    "release_date": "",
    "first_air_date": "",
    "poster_path": "",
    "backdrop_path": "",
    "genres": [],
    "credits": {"cast": [], "crew": []},
    "external_ids": {},
}


class MetadataManager:
    """元数据管理器"""

    def __init__(self, tmdb_api_key: str, language: str = "zh-CN"):
        """
        初始化元数据管理器

        Args:
            tmdb_api_key: TMDB API Key
            language: 返回语言，默认 zh-CN，可选 en-US
        """
        self.api_key = tmdb_api_key
        self.language = language
        self.base_url = "https://api.themoviedb.org/3"
        self.image_base_url = "https://image.tmdb.org/t/p/original"

    def generate_nfo(
        self,
        tmdb_id: str,
        media_type: str,
        output_path: str,
        title: str = None,
        year: str = None
    ) -> bool:
        """
        生成 NFO 元数据文件

        Args:
            tmdb_id: TMDB ID
            media_type: "movie" 或 "tv"
            output_path: NFO 文件输出路径
            title: 可选，作品标题（用于日志）
            year: 可选，年份（用于日志）

        Returns:
            bool: 是否成功
        """
        try:
            # ── 优先复用：NFO 文件已存在则跳过重新生成 ────────────────
            if os.path.exists(output_path):
                logger.info(f"[META] NFO 已存在，直接复用: {output_path}")
                return True

            # 从 TMDB 获取详细信息
            if media_type == "movie":
                details = self._fetch_movie_details(tmdb_id)
            else:
                details = self._fetch_tv_details(tmdb_id)

            if not details:
                logger.error(f"[META] 获取 TMDB 详情失败: {title or tmdb_id}")
                return False

            # 路径防穿越校验
            output_dir = os.path.dirname(os.path.abspath(output_path))
            try:
                safe_path = _validate_path(output_path, output_dir)
            except ValueError as ve:
                logger.error(str(ve))
                return False

            # 生成 XML
            if media_type == "movie":
                xml_content = self._build_movie_nfo(details)
            else:
                xml_content = self._build_tv_nfo(details)

            # 确保目录存在
            os.makedirs(output_dir, exist_ok=True)

            # 写入文件
            with open(str(safe_path), "w", encoding="utf-8") as f:
                f.write(xml_content)

            logger.info(f"[META] [STORAGE] NFO 生成成功: {safe_path}")
            return True

        except Exception as e:
            logger.error(f"[META] NFO 生成失败: {e}")
            return False

    def download_poster(
        self,
        tmdb_id: str,
        media_type: str,
        output_dir: str,
        title: str = None
    ) -> Optional[str]:
        """
        下载 TMDB 海报（Docker AIO 透明挂载模式）

        - 优先复用：若目标目录已存在 poster.jpg 或 poster.png，直接返回，不重复下载
        - 海报下载失败不抛出异常，返回 None
        - 路径防穿越校验
        - 使用 httpx + 重试机制

        Returns:
            Optional[str]: 海报本地路径，失败返回 None
        """
        try:
            # ── 优先复用：检查目标目录是否已有海报 ──────────────────
            output_dir_abs = str(Path(output_dir).resolve())
            for existing_name in ["poster.jpg", "poster.png"]:
                existing_path = os.path.join(output_dir_abs, existing_name)
                if os.path.exists(existing_path):
                    logger.info(f"[META] 海报已存在，直接复用: {existing_path}")
                    return existing_path
            # 从 TMDB 获取详细信息
            if media_type == "movie":
                details = self._fetch_movie_details(tmdb_id)
            else:
                details = self._fetch_tv_details(tmdb_id)

            if not details:
                logger.warning(f"[META] 获取 TMDB 详情失败，海报跳过: {title or tmdb_id}")
                return None

            poster_path = _safe_get(details, "poster_path", default="")
            if not poster_path:
                logger.warning(f"[META] 无海报数据: {title or tmdb_id}")
                return None

            # 构建海报 URL
            poster_url = f"{self.image_base_url}{poster_path}"

            # 下载海报（带重试）
            resp = _http_get_with_retry(poster_url, timeout=30.0)
            if not resp:
                logger.warning(f"[META] 海报下载失败（网络）: {title or tmdb_id}")
                return None

            # 路径防穿越校验
            output_dir_abs = str(Path(output_dir).resolve())
            raw_output_path = os.path.join(output_dir_abs, "poster.jpg")
            try:
                safe_path = _validate_path(raw_output_path, output_dir_abs)
            except ValueError as ve:
                logger.error(str(ve))
                return None

            # 确保目录存在
            os.makedirs(output_dir_abs, exist_ok=True)

            # 保存海报
            with open(str(safe_path), "wb") as f:
                f.write(resp.content)

            logger.info(f"[META] [STORAGE] 海报下载成功: {safe_path}")
            return str(safe_path)

        except Exception as e:
            logger.error(f"[META] 海报下载失败: {e}")
            return None

    def download_fanart(
        self,
        tmdb_id: str,
        media_type: str,
        output_dir: str,
        title: str = None
    ) -> Optional[str]:
        """
        下载 TMDB Fanart（背景图）

        Returns:
            Optional[str]: Fanart 本地路径，失败返回 None
        """
        try:
            # ── 优先复用：检查目标目录是否已有 Fanart ──────────────────
            output_dir_abs = str(Path(output_dir).resolve())
            for existing_name in ["fanart.jpg", "fanart.png"]:
                existing_path = os.path.join(output_dir_abs, existing_name)
                if os.path.exists(existing_path):
                    logger.info(f"[META] Fanart 已存在，直接复用: {existing_path}")
                    return existing_path

            if media_type == "movie":
                details = self._fetch_movie_details(tmdb_id)
            else:
                details = self._fetch_tv_details(tmdb_id)

            if not details:
                logger.warning(f"[META] 获取 TMDB 详情失败，Fanart 跳过: {title or tmdb_id}")
                return None

            backdrop_path = _safe_get(details, "backdrop_path", default="")
            if not backdrop_path:
                logger.warning(f"[META] 无 Fanart 数据: {title or tmdb_id}")
                return None

            fanart_url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"

            resp = _http_get_with_retry(fanart_url, timeout=30.0)
            if not resp:
                logger.warning(f"[META] Fanart 下载失败（网络）: {title or tmdb_id}")
                return None

            output_dir_abs = str(Path(output_dir).resolve())
            raw_output_path = os.path.join(output_dir_abs, "fanart.jpg")
            try:
                safe_path = _validate_path(raw_output_path, output_dir_abs)
            except ValueError as ve:
                logger.error(str(ve))
                return None

            os.makedirs(output_dir_abs, exist_ok=True)

            with open(str(safe_path), "wb") as f:
                f.write(resp.content)

            logger.info(f"[META] [STORAGE] Fanart 下载成功: {safe_path}")
            return str(safe_path)

        except Exception as e:
            logger.error(f"[META] Fanart 下载失败: {e}")
            return None

    def _fetch_movie_details(self, tmdb_id: str) -> Optional[Dict[str, Any]]:
        """获取电影详情（带重试，严谨 .get() 解析）"""
        try:
            url = f"{self.base_url}/movie/{tmdb_id}"
            params = {
                "api_key": self.api_key,
                "language": self.language,
                "append_to_response": "credits,external_ids"
            }
            resp = _http_get_with_retry(url, params=params)
            if not resp:
                logger.error(f"[META] 获取电影详情失败: tmdb_id={tmdb_id}")
                return None
            data = resp.json()
            # 核心字段缺失时返回空结果对象
            if not data.get("id"):
                logger.warning(f"[META] TMDB 返回数据缺少 id 字段: {data}")
                return EMPTY_DETAIL.copy()
            return data
        except Exception as e:
            logger.error(f"[META] 获取电影详情异常: {e}")
            return None

    def _fetch_tv_details(self, tmdb_id: str) -> Optional[Dict[str, Any]]:
        """获取剧集详情（带重试，严谨 .get() 解析）"""
        try:
            url = f"{self.base_url}/tv/{tmdb_id}"
            params = {
                "api_key": self.api_key,
                "language": self.language,
                "append_to_response": "credits,external_ids"
            }
            resp = _http_get_with_retry(url, params=params)
            if not resp:
                logger.error(f"[META] 获取剧集详情失败: tmdb_id={tmdb_id}")
                return None
            data = resp.json()
            if not data.get("id"):
                logger.warning(f"[META] TMDB 返回数据缺少 id 字段: {data}")
                return EMPTY_DETAIL.copy()
            return data
        except Exception as e:
            logger.error(f"[META] 获取剧集详情异常: {e}")
            return None

    def _escape_xml(self, text: str) -> str:
        """转义 XML 特殊字符"""
        if not text:
            return ""
        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        text = text.replace("'", "&apos;")
        return text

    def _build_movie_nfo(self, details: Dict[str, Any]) -> str:
        """构建电影 NFO XML（严谨 .get() 链式调用，杜绝 KeyError）"""
        root = ET.Element("movie")

        ET.SubElement(root, "title").text = self._escape_xml(_safe_get(details, "title"))
        ET.SubElement(root, "originaltitle").text = self._escape_xml(_safe_get(details, "original_title"))
        ET.SubElement(root, "plot").text = self._escape_xml(_safe_get(details, "overview"))
        ET.SubElement(root, "tagline").text = self._escape_xml(_safe_get(details, "tagline"))
        ET.SubElement(root, "runtime").text = str(_safe_get(details, "runtime",             default=0))

        ET.SubElement(root, "rating").text = str(_safe_get(details, "vote_average", default=0))
        ET.SubElement(root, "votes").text = str(_safe_get(details, "vote_count", default=0))

        release_date = _safe_get(details, "release_date", default="")
        if release_date and len(str(release_date)) >= 4:
            ET.SubElement(root, "year").text = str(release_date)[:4]
            ET.SubElement(root, "premiered").text = str(release_date)

        ET.SubElement(root, "tmdbid").text = str(_safe_get(details, "id", default=""))
        imdb_id = _safe_get(details, "external_ids", "imdb_id", default="")
        if imdb_id:
            ET.SubElement(root, "imdbid").text = imdb_id

        # TMM 3.1.x 兼容：写入 <uniqueid> 节点
        _tmdb_val = str(_safe_get(details, "id", default=""))
        if _tmdb_val:
            _uid_tmdb = ET.SubElement(root, "uniqueid")
            _uid_tmdb.set("type", "tmdb")
            _uid_tmdb.set("default", "true")
            _uid_tmdb.text = _tmdb_val
        if imdb_id:
            _uid_imdb = ET.SubElement(root, "uniqueid")
            _uid_imdb.set("type", "imdb")
            _uid_imdb.text = imdb_id

        for genre in _safe_get(details, "genres", default=[]):
            name = _safe_get(genre, "name", default="")
            if name:
                ET.SubElement(root, "genre").text = name

        cast = _safe_get(details, "credits", "cast", default=[])
        for actor in cast[:10]:
            actor_elem = ET.SubElement(root, "actor")
            ET.SubElement(actor_elem, "name").text = _safe_get(actor, "name", default="")
            ET.SubElement(actor_elem, "role").text = _safe_get(actor, "character", default="")
            profile = _safe_get(actor, "profile_path", default="")
            if profile:
                ET.SubElement(actor_elem, "thumb").text = f"{self.image_base_url}{profile}"

        crew = _safe_get(details, "credits", "crew", default=[])
        for member in crew:
            if _safe_get(member, "job") == "Director":
                ET.SubElement(root, "director").text = _safe_get(member, "name", default="")

        poster = _safe_get(details, "poster_path", default="")
        if poster:
            ET.SubElement(root, "thumb").text = f"{self.image_base_url}{poster}"

        backdrop = _safe_get(details, "backdrop_path", default="")
        if backdrop:
            ET.SubElement(root, "fanart").text = f"{self.image_base_url}{backdrop}"

        return self._prettify_xml(root)

    def _build_tv_nfo(self, details: Dict[str, Any]) -> str:
        """构建剧集 NFO XML（严谨 .get() 链式调用，杜绝 KeyError）"""
        root = ET.Element("tvshow")

        ET.SubElement(root, "title").text = self._escape_xml(_safe_get(details, "name"))
        ET.SubElement(root, "originaltitle").text = self._escape_xml(_safe_get(details, "original_name"))
        ET.SubElement(root, "plot").text = self._escape_xml(_safe_get(details, "overview"))

        ET.SubElement(root, "rating").text = str(_safe_get(details, "vote_average", default=0))
        ET.SubElement(root, "votes").text = str(_safe_get(details, "vote_count", default=0))

        first_air_date = _safe_get(details, "first_air_date", default="")
        if first_air_date and len(str(first_air_date)) >= 4:
            ET.SubElement(root, "year").text = str(first_air_date)[:4]
            ET.SubElement(root, "premiered").text = str(first_air_date)

        ET.SubElement(root, "tmdbid").text = str(_safe_get(details, "id", default=""))
        imdb_id = _safe_get(details, "external_ids", "imdb_id", default="")
        if imdb_id:
            ET.SubElement(root, "imdbid").text = imdb_id

        # TMM compatibility: write <uniqueid> nodes
        _tmdb_val = str(_safe_get(details, "id", default=""))
        if _tmdb_val:
            _uid_tmdb = ET.SubElement(root, "uniqueid")
            _uid_tmdb.set("type", "tmdb")
            _uid_tmdb.set("default", "true")
            _uid_tmdb.text = _tmdb_val
        if imdb_id:
            _uid_imdb = ET.SubElement(root, "uniqueid")
            _uid_imdb.set("type", "imdb")
            _uid_imdb.text = imdb_id

        for genre in _safe_get(details, "genres", default=[]):
            name = _safe_get(genre, "name", default="")
            if name:
                ET.SubElement(root, "genre").text = name

        cast = _safe_get(details, "credits", "cast", default=[])
        for actor in cast[:10]:
            actor_elem = ET.SubElement(root, "actor")
            ET.SubElement(actor_elem, "name").text = _safe_get(actor, "name", default="")
            ET.SubElement(actor_elem, "role").text = _safe_get(actor, "character", default="")
            profile = _safe_get(actor, "profile_path", default="")
            if profile:
                ET.SubElement(actor_elem, "thumb").text = f"{self.image_base_url}{profile}"

        poster = _safe_get(details, "poster_path", default="")
        if poster:
            ET.SubElement(root, "thumb").text = f"{self.image_base_url}{poster}"

        backdrop = _safe_get(details, "backdrop_path", default="")
        if backdrop:
            ET.SubElement(root, "fanart").text = f"{self.image_base_url}{backdrop}"

        return self._prettify_xml(root)

    def _prettify_xml(self, elem: ET.Element) -> str:
        """格式化 XML 输出"""
        from xml.dom import minidom
        rough_string = ET.tostring(elem, encoding="utf-8")
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding="utf-8").decode("utf-8")
