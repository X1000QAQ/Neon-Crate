"""

TMDB 元数据适配器 - 搜索、详情和外部 ID 统一封装。



职责：

- 封装 TMDB movie / tv / multi 搜索端点，向上返回原始但稳定的字典列表。

- 根据 `rename_lang` 和 `poster_lang` 分别控制文本语言和图片语言。

- 使用统一 HTTP 重试工具处理网络波动、超时和 429 限流。

- 提供电影详情、剧集详情和 IMDb 等外部 ID 查询接口。



搜索策略：

- 优先调用类型精确端点：电影走 `/search/movie`，剧集走 `/search/tv`。

- 精确端点无结果时降级到 `/search/multi`，并过滤 `person` 结果。

- 本模块不判断“最佳匹配”，候选排序和防重由刮削任务链路处理。



边界：

- 不写数据库，不写文件，不生成 NFO。

- 不负责 AI 文件名语义识别，也不恢复用户自定义正则清洗能力。

"""

from typing import Optional, List, Dict, Any

import logging

from app.infra.http_utils import http_get_with_retry as _http_get_with_retry



logger = logging.getLogger(__name__)





class TMDBAdapter:

    """
    TMDB 元数据适配器。

    本类只封装上游 API 调用和语言参数，不保存状态到数据库。
    调用方负责：
    - 选择最终候选。
    - 判断是否重复入库。
    - 决定 NFO / 海报写入位置。
    """



    def __init__(self, api_key: str, rename_lang: str = "zh", poster_lang: str = "zh"):

        """

        初始化 TMDB 适配器



        Args:

            api_key: TMDB API Key

            rename_lang: 文本/标题语言偏好，"zh" 使用 zh-CN，"en" 使用 en-US

            poster_lang: 海报/图片语言偏好，"zh" 使用 zh，"en" 使用 en

        """

        self.api_key = api_key

        self.text_lang = "zh-CN" if rename_lang == "zh" else "en-US"

        self.image_lang = "zh" if poster_lang == "zh" else "en"

        self.base_url = "https://api.themoviedb.org/3"

        logger.info(f"[TMDB] TMDB 适配器初始化完成，文本语言: {self.text_lang}，图片语言: {self.image_lang}")



    def search_media(self, query: str, media_type: str = "movie", year: Optional[str] = None) -> List[Dict]:

        """

        统一搜索入口：动态路由 + /search/multi 降级



        Args:

            query:      搜索关键词

            media_type: "movie" 或 "tv"

            year:       年份（可选）



        路由策略：

        1. 精确端点：media_type=="tv" → /search/tv，否则 → /search/movie

        2. 终极降级：精确端点返回 0 个结果时，自动请求 /search/multi

           并过滤掉 media_type=="person" 的脏数据

        """

        log_type = "剧集" if media_type == "tv" else "电影"

        endpoint = "/search/tv" if media_type == "tv" else "/search/movie"

        logger.info(f"[TMDB] 搜索{log_type}: '{query}' → {endpoint}")



        # 精确端点参数

        params: dict = {

            "api_key": self.api_key,

            "query": query,

            "language": self.text_lang,

            "include_adult": "false",

        }

        if year:

            if media_type == "tv":

                params["first_air_date_year"] = year

            else:

                params["primary_release_year"] = year



        results: List[Dict] = []

        try:

            resp = _http_get_with_retry(f"{self.base_url}{endpoint}", params=params, timeout=15.0)

            if resp:

                results = resp.json().get("results", [])

                logger.info(f"[TMDB] {endpoint} 返回 {len(results)} 条结果")

        except Exception as e:

            logger.error(f"[TMDB] {endpoint} 请求失败: {e}")



        # fallback：精确端点无结果时请求 /search/multi

        if not results:

            logger.info(f"[TMDB] {log_type}端点无结果，降级 /search/multi: '{query}'")

            multi_params = {

                "api_key": self.api_key,

                "query": query,

                "language": self.text_lang,

                "include_adult": "false",

            }

            try:

                resp = _http_get_with_retry(f"{self.base_url}/search/multi", params=multi_params, timeout=15.0)

                if resp:

                    raw = resp.json().get("results", [])

                    # 过滤 person 脏数据，并标记 media_type

                    results = [r for r in raw if r.get("media_type") != "person"]

                    logger.info(f"[TMDB] /search/multi 返回 {len(results)} 条（过滤 person 后）")

            except Exception as e:

                logger.error(f"[TMDB] /search/multi 失败: {e}")



        return results



    def search_movie(self, query: str, year: Optional[str] = None) -> List[Dict]:

        """

        搜索电影



        Args:

            query: 搜索关键词

            year: 年份（可选）



        Returns:

            电影列表（可能为空列表）

        """

        params = {

            "api_key": self.api_key,

            "query": query,

            "language": self.text_lang,

            "include_adult": "false",

        }

        if year:

            params["primary_release_year"] = year



        url = f"{self.base_url}/search/movie"

        try:

            resp = _http_get_with_retry(url, params=params)

            if not resp:

                logger.error(f"[TMDB] 搜索电影失败: {query}")

                return []



            results = resp.json().get("results", [])

            logger.info(f"[TMDB] 搜索电影: '{query}' -> {len(results)} 个结果")

            return results

        except Exception as e:

            logger.error(f"[TMDB] 解析搜索结果失败: {e}")

            return []



    def search_tv(self, query: str, year: Optional[str] = None) -> List[Dict]:

        """

        搜索剧集



        Args:

            query: 搜索关键词

            year: 年份（可选）



        Returns:

            剧集列表（可能为空列表）

        """

        params = {

            "api_key": self.api_key,

            "query": query,

            "language": self.text_lang,

            "include_adult": "false",

        }

        if year:

            params["first_air_date_year"] = year



        url = f"{self.base_url}/search/tv"

        try:

            resp = _http_get_with_retry(url, params=params)

            if not resp:

                logger.error(f"[TMDB] 搜索剧集失败: {query}")

                return []



            results = resp.json().get("results", [])

            logger.info(f"[TMDB] 搜索剧集: '{query}' -> {len(results)} 个结果")

            return results

        except Exception as e:

            logger.error(f"[TMDB] 解析搜索结果失败: {e}")

            return []



    def get_movie_details(self, tmdb_id: str) -> Optional[Dict]:

        """

        获取电影详情



        Args:

            tmdb_id: TMDB ID



        Returns:

            电影详情字典，失败返回 None

        """

        params = {

            "api_key": self.api_key,

            "language": self.text_lang,

            "include_image_language": f"{self.image_lang},null",

            "append_to_response": "credits,external_ids",

        }

        url = f"{self.base_url}/movie/{tmdb_id}"

        resp = _http_get_with_retry(url, params=params)

        if not resp:

            logger.error(f"[TMDB] 获取电影详情失败: tmdb_id={tmdb_id}")

            return None

        try:

            return resp.json()

        except Exception as e:

            logger.error(f"[TMDB] 解析电影详情失败: {e}")

            return None



    def get_tv_details(self, tmdb_id: str) -> Optional[Dict]:

        """

        获取剧集详情



        Args:

            tmdb_id: TMDB ID



        Returns:

            剧集详情字典，失败返回 None

        """

        params = {

            "api_key": self.api_key,

            "language": self.text_lang,

            "include_image_language": f"{self.image_lang},null",

            "append_to_response": "credits,external_ids",

        }

        url = f"{self.base_url}/tv/{tmdb_id}"

        resp = _http_get_with_retry(url, params=params)

        if not resp:

            logger.error(f"[TMDB] 获取剧集详情失败: tmdb_id={tmdb_id}")

            return None

        try:

            return resp.json()

        except Exception as e:

            logger.error(f"[TMDB] 解析剧集详情失败: {e}")

            return None



    def get_external_ids(self, tmdb_id: str, media_type: str) -> Dict[str, str]:

        """

        获取外部 ID（IMDB 等）



        Args:

            tmdb_id: TMDB ID

            media_type: "movie" 或 "tv"



        Returns:

            外部 ID 字典，失败返回空字典

        """

        endpoint = "movie" if media_type == "movie" else "tv"

        url = f"{self.base_url}/{endpoint}/{tmdb_id}/external_ids"

        params = {"api_key": self.api_key}

        resp = _http_get_with_retry(url, params=params)

        if not resp:

            logger.warning(f"[TMDB] 获取外部 ID 失败: tmdb_id={tmdb_id}")

            return {}

        try:

            return resp.json()

        except Exception as e:

            logger.error(f"[TMDB] 解析外部 ID 失败: {e}")

            return {}

