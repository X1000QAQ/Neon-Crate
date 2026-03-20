"""
nfo_parser.py — NFO 本地真理解析器

双轨隔离架构中「自动刮削轨」的核心组件。

全兼容：
  - Neon Crate 自研格式（<tmdbid> + <imdbid> 直接节点）
  - TMM 3.1.x 格式（movie.nfo 的 <uniqueid type="tmdb"> / <uniqueid type="imdb"> / <id>）
  - tvshow.nfo（<tmdbid> + <imdbid> 直接节点）

支持根节点：<movie> 和 <tvshow>（兜底：任意根节点）

严格遵守双轨隔离原则：
  - 本模块只供「自动刮削轨」（perform_scrape_all_task_sync）调用
  - 「手动核武轨」（manual_rebuild）禁止调用本模块
"""
import re
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# 季目录名正则：Season 1 / S01 / Specials 等变体
_SEASON_DIR_RE = re.compile(
    r'^(Season|S)\s*\d+$|^Specials$',
    re.IGNORECASE,
)

# ── NFO 解析三层防御体系 ───────────────────────────────────────────
# 目标：面对第三方“脏 NFO/脏 XML”保持极强生存能力。
#
# 第一层：errors=replace（读取容错，抵抗错误编码/二进制污染）
# 第二层：生化清洗（BOM/HTML 实体/裸 &/控制字符归一化与剔除）
# 第三层：正则兜底（ET 彻底失败时抢救 tmdb/imdb/title/year 关键字段）
#
# 🚨 架构师警告（DO NOT MODIFY）：
# - 此模块属于「自动刮削轨」的本地真理解析器；任何改动都可能影响 NFO 短路与防重熔断链路。
# - 「手动核武轨 manual_rebuild」禁止调用本模块（双轨隔离）。
# -------------------------------------------------------------------
#
# ── XML 预处理清洗层 ──────────────────────────────────────────────
# 匹配未转义的裸 &（后面不是合法 XML 实体序列）
_BARE_AMP_RE = re.compile(r'&(?!(?:#\d+|#x[0-9a-fA-F]+|amp|lt|gt|quot|apos);)')
# XML 1.0 禁止的控制字符（排除 \t \n \r）
_CTRL_CHAR_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
# 常见 HTML 实体 → XML 安全替换表
_HTML_ENTITIES: Dict[str, str] = {
    '&nbsp;': ' ', '&copy;': '©', '&reg;': '®', '&trade;': '™',
    '&mdash;': '—', '&ndash;': '–', '&hellip;': '…',
    '&laquo;': '"', '&raquo;': '"',
}


def _sanitize_xml(raw: str) -> str:
    """
    XML 内容预清洗：在严格解析前归一化常见毒化输入。

    处理顺序（顺序不可颠倒）：
    1. 剥除 UTF-8 BOM
    2. 替换已知 HTML 实体（避免与步骤 3 裸 & 转义相互干扰）
    3. 将裸 & 替换为 &amp;
    4. 剔除 XML 1.0 禁止的控制字符
    """
    raw = raw.lstrip('\ufeff')                        # 1. BOM
    for ent, repl in _HTML_ENTITIES.items():          # 2. HTML 实体
        raw = raw.replace(ent, repl)
    raw = _BARE_AMP_RE.sub('&amp;', raw)              # 3. 裸 &
    raw = _CTRL_CHAR_RE.sub('', raw)                  # 4. 控制字符
    return raw


# ── 正则兜底层（ET 彻底失败时抢救关键字段）──────────────────────
_RE_TITLE    = re.compile(r'<title[^>]*>\s*([^<]+?)\s*</title>', re.S)
_RE_YEAR     = re.compile(r'<year[^>]*>\s*(\d{4})\s*</year>', re.S)
_RE_TMDBID   = re.compile(r'<tmdbid[^>]*>\s*(\d+)\s*</tmdbid>', re.S | re.I)
_RE_IMDBID   = re.compile(r'<(?:imdbid|id)[^>]*>\s*(tt\d+)\s*</(?:imdbid|id)>', re.S | re.I)
_RE_UNIQUEID = re.compile(
    r'<uniqueid[^>]*type=["\']([^"\']+)["\'][^>]*>\s*([^<]+?)\s*</uniqueid>',
    re.S | re.I,
)


def _regex_fallback(raw: str) -> Dict[str, Optional[str]]:
    """当 ET 彻底失败时，用正则从原始文本中抢救关键字段。"""
    result: Dict[str, Optional[str]] = {
        "tmdb_id": None, "imdb_id": None,
        "title": None, "year": None, "plot": None,
    }
    m = _RE_TITLE.search(raw)
    if m:
        result["title"] = m.group(1).strip() or None
    m = _RE_YEAR.search(raw)
    if m:
        result["year"] = m.group(1).strip() or None
    m = _RE_TMDBID.search(raw)
    if m:
        result["tmdb_id"] = m.group(1).strip() or None
    m = _RE_IMDBID.search(raw)
    if m:
        result["imdb_id"] = m.group(1).strip() or None
    # <uniqueid type="tmdb"> / <uniqueid type="imdb"> 兜底
    if not result["tmdb_id"] or not result["imdb_id"]:
        for uid_type, uid_val in _RE_UNIQUEID.findall(raw):
            t = uid_type.lower().strip()
            v = uid_val.strip()
            if t == 'tmdb' and not result["tmdb_id"]:
                result["tmdb_id"] = v or None
            elif t == 'imdb' and not result["imdb_id"]:
                result["imdb_id"] = v or None
    return result


def find_nfo(video_path: str) -> Optional[str]:
    """
    智能 NFO 寻址：同级目录 → 季目录向上回溯。

    寻址顺序：
    1. 同级目录的 movie.nfo
    2. 同级目录的 tvshow.nfo
    3. 与视频同名的 .nfo（Plex / Emby 风格，如 S01E01.nfo）
    4. 若当前目录名匹配 Season 正则 → 回溯到父目录再依次寻找
       tvshow.nfo / movie.nfo

    Args:
        video_path: 视频文件的绝对路径

    Returns:
        找到的 NFO 文件绝对路径；未找到返回 None
    """
    p = Path(video_path)
    video_dir = p.parent

    # Step 1：同级目录
    for nfo_name in ["movie.nfo", "tvshow.nfo", f"{p.stem}.nfo"]:
        candidate = video_dir / nfo_name
        if candidate.is_file():
            logger.debug(f"[NfoParser] 同级找到 NFO: {candidate}")
            return str(candidate)

    # Step 2：季目录向上回溯
    if _SEASON_DIR_RE.match(video_dir.name):
        parent_dir = video_dir.parent
        for nfo_name in ["tvshow.nfo", "movie.nfo"]:
            candidate = parent_dir / nfo_name
            if candidate.is_file():
                logger.debug(f"[NfoParser] 回溯找到 NFO: {candidate}")
                return str(candidate)

    logger.debug(f"[NfoParser] 未找到 NFO: {video_path}")
    return None


def parse_nfo(file_path: str) -> Dict[str, Optional[str]]:
    """
    解析 NFO 文件，返回标准化字典。

    字段提取优先级：

    tmdb_id:
        1. <tmdbid>  （Neon 自研 / TMM tvshow 格式）
        2. <uniqueid type="tmdb">  （TMM movie 格式 fallback）

    imdb_id:
        1. <imdbid>  （Neon 自研 / TMM tvshow 格式）
        2. <uniqueid type="imdb">  （TMM movie 格式）
        3. <id>  （仅当值以 "tt" 开头时采用，TMM legacy 字段）

    title:  <title>
    year:   <year>
    plot:   <plot>

    Args:
        file_path: NFO 文件的绝对路径

    Returns:
        dict，所有值为 str 或 None。调用方负责 int() 转换。
        容错：解析失败时返回全 None 的字典（不抛出异常）。

    Raises:
        本函数设计为“永不向上传播异常”（生存优先）。所有异常均被捕获并降级为返回空字段字典。
    """
    result: Dict[str, Optional[str]] = {
        "tmdb_id": None,
        "imdb_id": None,
        "title":   None,
        "year":    None,
        "plot":    None,
    }
    try:
        # ── 第一层：读取原始文本（errors=replace 防止二进制污染崩溃）──
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read()

        # ── 第二层：预处理清洗 + ET 严格解析 ──────────────────────────
        cleaned = _sanitize_xml(raw)
        try:
            root = ET.fromstring(cleaned)

            # ── 基础字段 ────────────────────────────────────────────
            result["title"] = (root.findtext("title") or "").strip() or None
            result["year"]  = (root.findtext("year")  or "").strip() or None
            result["plot"]  = (root.findtext("plot")  or "").strip() or None
            result["showtitle"] = (root.findtext("showtitle") or "").strip()

            # ── tmdb_id：优先 <tmdbid>，回退 <uniqueid type="tmdb"> ────
            tmdb_id = (root.findtext("tmdbid") or "").strip()
            if not tmdb_id:
                for uid in root.findall("uniqueid"):
                    if (uid.get("type") or "").lower() == "tmdb":
                        tmdb_id = (uid.text or "").strip()
                        if tmdb_id:
                            break
            result["tmdb_id"] = tmdb_id or None

            # ── imdb_id：<imdbid> → <uniqueid type="imdb"> → <id>(tt) ──
            imdb_id = (root.findtext("imdbid") or "").strip()
            if not imdb_id:
                for uid in root.findall("uniqueid"):
                    if (uid.get("type") or "").lower() == "imdb":
                        imdb_id = (uid.text or "").strip()
                        if imdb_id:
                            break
            if not imdb_id:
                legacy_id = (root.findtext("id") or "").strip()
                if legacy_id.lower().startswith("tt"):
                    imdb_id = legacy_id
            result["imdb_id"] = imdb_id or None

            logger.debug(
                f"[NfoParser] 解析完成: {file_path} "
                f"tmdb={result['tmdb_id']} imdb={result['imdb_id']} "
                f"title={result['title']}"
            )

        except ET.ParseError as xml_err:
            # ── 第三层：正则兜底（ET 仍失败时抢救关键字段）──────────
            logger.warning(f"[NfoParser] XML 解析失败（启用正则兜底）: {file_path} — {xml_err}")
            fallback = _regex_fallback(raw)
            if any(v for v in fallback.values()):
                logger.info(
                    f"[NfoParser] 正则兜底成功: {file_path} "
                    f"tmdb={fallback['tmdb_id']} imdb={fallback['imdb_id']} "
                    f"title={fallback['title']}"
                )
                return fallback
            logger.warning(f"[NfoParser] 正则兜底亦无结果，返回空字典: {file_path}")

    except FileNotFoundError:
        logger.warning(f"[NfoParser] NFO 文件不存在: {file_path}")
    except Exception as e:
        logger.warning(f"[NfoParser] 未知解析错误: {file_path} — {e}")

    return result


def get_tvshow_gold_standard(video_path: str):
    """
    向上最多回溯 3 层目录查找 tvshow.nfo，获取剧集金标准身份。
    返回含 title/tmdb_id/imdb_id/year 的字典（仅当 tmdb_id 有效时）；否则返回 None。
    身份隔离：以剧集根 tvshow.nfo 为金标，避免单集 NFO 内 episode 级 ID 上升污染整剧身份（TMM3 等工具并存场景）。
    """
    from pathlib import Path
    try:
        current_dir = Path(video_path).parent
        for _ in range(3):
            nfo_path = current_dir / "tvshow.nfo"
            if nfo_path.exists() and nfo_path.is_file():
                try:
                    result = parse_nfo(str(nfo_path))
                    if result.get("tmdb_id"):
                        return result
                except Exception:
                    pass
            current_dir = current_dir.parent
    except Exception:
        pass
    return None
