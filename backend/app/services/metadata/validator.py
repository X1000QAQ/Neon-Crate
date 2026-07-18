"""
TMDB 元数据校验防火墙。

职责：
- 在归档路径生成和文件写入前，校验 AI 提取的剧集季 / 集坐标是否真实存在于 TMDB。
- 对非剧集媒体直接跳过校验，保持电影链路轻量。
- 返回规范化校验结果，供刮削任务决定继续归档、失败中断或提示建议坐标。

返回语义：
- `ok=True`：允许继续归档。
- `status="skipped"`：非 TV 媒体，无需单集校验。
- `status="failed"`：缺少 API Key、TMDB ID、季集坐标非法或 TMDB 单集不存在。

边界：
- 本模块只做只读上游校验，不写数据库、不移动文件、不生成 NFO。
- 建议坐标仅供调用方参考，不在本函数内自动修改任务数据。
"""
import logging
from typing import Any, Dict, Optional

from app.infra.http_utils import http_get_with_retry

logger = logging.getLogger(__name__)


def validate_tmdb_metadata(
    tmdb_api_key: str,
    tmdb_id: int | str,
    media_type: str,
    season: Optional[int] = None,
    episode: Optional[int] = None,
    language: str = "zh-CN",
) -> Dict[str, Any]:
    """
    校验 AI / TMDB 链路得到的单集坐标是否可归档。

    校验流程：
    1. 非 TV 媒体直接返回 skipped。
    2. 校验 TMDB API Key、TMDB ID、season、episode 是否存在且可转为正整数。
    3. 请求 `/tv/{tmdb_id}/season/{season}/episode/{episode}`。
    4. 200 表示单集存在；其他结果返回失败并附带建议 season / episode。

    Returns:
        Dict[str, Any]: 规范化结果字典，包含：
            - ok: 是否允许归档继续。
            - status: `ok` / `skipped` / `failed`。
            - reason: 机器可读失败或跳过原因。
            - suggested_season: 可选建议季号。
            - suggested_episode: 可选建议集号。
    """
    normalized_type = (media_type or "").strip().lower()
    if normalized_type != "tv":
        return {
            "ok": True,
            "status": "skipped",
            "reason": "non_tv_media",
            "tmdb_id": tmdb_id,
            "media_type": normalized_type,
        }

    if not tmdb_api_key or not str(tmdb_api_key).strip():
        return {
            "ok": False,
            "status": "failed",
            "reason": "missing_tmdb_api_key",
            "tmdb_id": tmdb_id,
            "season": season,
            "episode": episode,
        }

    if not tmdb_id:
        return {
            "ok": False,
            "status": "failed",
            "reason": "missing_tmdb_id",
            "tmdb_id": tmdb_id,
            "season": season,
            "episode": episode,
        }

    if season is None or episode is None:
        return {
            "ok": False,
            "status": "failed",
            "reason": "missing_tv_episode_coordinates",
            "tmdb_id": tmdb_id,
            "season": season,
            "episode": episode,
            "suggested_season": 1 if season not in (None, 1) else season,
            "suggested_episode": episode,
        }

    try:
        season_int = int(season)
        episode_int = int(episode)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "status": "failed",
            "reason": "invalid_tv_episode_coordinates",
            "tmdb_id": tmdb_id,
            "season": season,
            "episode": episode,
            "suggested_season": 1,
            "suggested_episode": episode,
        }

    if season_int <= 0 or episode_int <= 0:
        return {
            "ok": False,
            "status": "failed",
            "reason": "non_positive_tv_episode_coordinates",
            "tmdb_id": tmdb_id,
            "season": season_int,
            "episode": episode_int,
            "suggested_season": 1 if season_int != 1 else season_int,
            "suggested_episode": episode_int if episode_int > 0 else None,
        }

    url = f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season_int}/episode/{episode_int}"
    params = {
        "api_key": tmdb_api_key,
        "language": language,
    }

    try:
        resp = http_get_with_retry(url, params=params, timeout=15.0)
    except Exception as exc:
        logger.warning(
            "[TMDB][FIREWALL] 单集校验异常: tmdb_id=%s S%02dE%02d | %s",
            tmdb_id,
            season_int,
            episode_int,
            exc,
        )
        return {
            "ok": False,
            "status": "failed",
            "reason": "tmdb_validation_exception",
            "tmdb_id": tmdb_id,
            "season": season_int,
            "episode": episode_int,
            "suggested_season": 1 if season_int != 1 else season_int,
            "suggested_episode": episode_int,
        }

    if resp is not None and resp.status_code == 200:
        logger.info(
            "[TMDB][FIREWALL] 单集校验通过: tmdb_id=%s S%02dE%02d",
            tmdb_id,
            season_int,
            episode_int,
        )
        return {
            "ok": True,
            "status": "ok",
            "reason": "episode_exists",
            "tmdb_id": tmdb_id,
            "season": season_int,
            "episode": episode_int,
        }

    suggested_season = 1 if season_int != 1 else season_int
    result = {
        "ok": False,
        "status": "failed",
        "reason": "episode_not_found_on_tmdb",
        "tmdb_id": tmdb_id,
        "season": season_int,
        "episode": episode_int,
        "suggested_season": suggested_season,
        "suggested_episode": episode_int,
    }
    logger.warning(
        "[TMDB][FIREWALL] 单集校验失败: tmdb_id=%s S%02dE%02d | suggested=S%02dE%02d",
        tmdb_id,
        season_int,
        episode_int,
        suggested_season,
        episode_int,
    )
    return result
