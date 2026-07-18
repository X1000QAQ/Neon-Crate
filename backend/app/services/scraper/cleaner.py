"""
结构化文件名工具 - 确定性坐标提取与归档路径安全化。

架构边界：
- 语义识别由 AI Agent 负责，包括片名、类型、年份、季集语义和噪声判断。
- 本模块不连接数据库，不读取 RegexLab，不执行用户自定义文件名物理正则清洗。
- 本模块只做确定性、可解释的结构化操作：扩展名剥离、括号清理、季集坐标提取、路径非法字符处理。

公共 API：
- `sanitize_filename(name)`：生成可落盘的安全目录名 / 文件名。
- `clean_name(filename)`：轻量结构化片名，供兼容和兜底展示使用。
- `extract_year()` / `extract_season_episode()`：从原始文件名提取显式坐标。
- `clean_and_extract(filename)`：一次性返回结构化字段和广告片段判断。

注意：
- “正则”在这里仅用于固定格式提取和路径安全处理，不用于替代 AI 做影视名称语义清洗。
"""
import re
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)

# ── 结构化提取（固定契约，不参与 RegexLab 式噪声删除）────────────────
_YEAR_PATTERN = re.compile(
    r'[\(\[\.\s]+(19\d{2}|20\d{2})[\)\]\.\s]+|'
    r'\b(19\d{2}|20\d{2})\b'
)

_SEASON_EPISODE_PATTERNS: List[re.Pattern] = [
    re.compile(r'[Ss](\d{1,2})[\s\._-]*[Ee](\d{1,3})'),
    re.compile(r'[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee](?:pisode)?[\s\._-]*(\d{1,3})', re.IGNORECASE),
    re.compile(r'(\d{1,2})x(\d{1,3})'),
    re.compile(r'[Ee][Pp]?[\s\._-]*(\d{1,3})'),
    re.compile(r'第[\s\._-]*(\d{1,3})[\s\._-]*[集话話]'),
]

_ANIME_EPISODE_PATTERN = re.compile(r'[-\s](\d{2,4})(?=\s*\[)')
_EXTENSION_PATTERN = re.compile(
    r'\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|mpg|mpeg|ts|m2ts|iso|rmvb|rm)$',
    re.IGNORECASE,
)
_SYMBOL_CLEANUP = re.compile(r'[_\.\-\+]+')
_COLON_PATTERN = re.compile(r'[\uff1a]')
_SE_TRUNCATE = re.compile(r'\b(?:[Ss]\d{1,2}[Ee]\d{1,3}|\d{1,2}x\d{1,3})\b')

_AD_KEYWORDS = [
    '澳门首家', '最新地址', '更多资源', '高清下载',
    '在线观看', '免费下载', 'BT下载', '磁力链接',
    '精彩推荐', '更多精彩', 'Sample', 'Trailer',
]


class MediaCleaner:
    """
    无状态结构化文件名工具。

    设计原则：
    - 可重复：同一输入始终返回同一输出。
    - 无副作用：不访问数据库，不读取配置，不写文件。
    - 非语义：不尝试判断真实影视名称，只提取显式结构和处理落盘安全字符。
    """

    def clean_name(self, filename: str) -> str:
        """
        轻量结构化片名：去扩展名、剥离方括号标签、季集前截断、符号归一化。
        噪声标签（分辨率/压制组等）交由 AI 语义层处理，此处不做删除。
        """
        if not filename:
            return ''

        cleaned = _EXTENSION_PATTERN.sub('', filename)
        cleaned = re.sub(r'^\s*\[[^\]]{1,20}\]\s*', '', cleaned)
        cleaned = re.sub(r'\[[^\]]*\]', ' ', cleaned)

        se_match = _SE_TRUNCATE.search(cleaned)
        if se_match:
            before = cleaned[:se_match.start()].strip()
            if before:
                cleaned = before

        cleaned = _COLON_PATTERN.sub(':', cleaned)
        cleaned = _SYMBOL_CLEANUP.sub(' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = cleaned.strip('.-_[]{}() ')

        logger.debug(f'[CLEAN] {filename} -> {cleaned}')
        return cleaned

    def extract_year(self, filename: str) -> Optional[int]:
        if not filename:
            return None
        match = _YEAR_PATTERN.search(filename)
        if match:
            year_str = match.group(1) or match.group(2)
            if year_str:
                try:
                    year = int(year_str)
                    if 1900 <= year <= 2100:
                        return year
                except ValueError:
                    pass
        return None

    def extract_season_episode(self, filename: str) -> Tuple[Optional[int], Optional[int]]:
        if not filename:
            return (None, None)

        for pattern in _SEASON_EPISODE_PATTERNS:
            match = pattern.search(filename)
            if match:
                groups = match.groups()
                try:
                    if len(groups) == 2:
                        return (int(groups[0]), int(groups[1]))
                    if len(groups) == 1:
                        return (1, int(groups[0]))
                except (ValueError, IndexError):
                    continue

        anime_match = _ANIME_EPISODE_PATTERN.search(filename)
        if anime_match:
            try:
                return (1, int(anime_match.group(1)))
            except (ValueError, IndexError):
                pass

        return (None, None)

    def is_tv_show(self, filename: str) -> bool:
        season, episode = self.extract_season_episode(filename)
        return season is not None or episode is not None

    def is_advertisement(self, filename: str) -> bool:
        if not filename:
            return True
        cleaned = self.clean_name(filename)
        if not cleaned or len(cleaned) < 2:
            return True
        filename_lower = filename.lower()
        for keyword in _AD_KEYWORDS:
            if keyword.lower() in filename_lower:
                if len(cleaned) < len(keyword) * 2:
                    logger.debug(f'[AD] {filename} -> 检测为广告')
                    return True
        return False

    @classmethod
    def sanitize_filename(cls, name: str) -> str:
        """归档路径安全化：智能冒号 + Windows 非法字符剥离。"""
        if not name:
            return ''

        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', name))
        if has_chinese:
            name = re.sub(r'[:\uf03a\ua789\uff1a]', '：', name)
        else:
            name = re.sub(r'[:\uf03a\ua789\uff1a]', ' - ', name)

        name = re.sub(r'[<>"/\\|?*]', ' ', name)
        name = re.sub(r' +', ' ', name).strip()
        return name

    def clean_and_extract(self, filename: str) -> dict:
        clean_name = self.clean_name(filename)
        year = self.extract_year(filename)
        season, episode = self.extract_season_episode(filename)
        result = {
            'clean_name': clean_name,
            'year': year,
            'season': season,
            'episode': episode,
            'is_tv': season is not None or episode is not None,
            'is_ad': self.is_advertisement(filename),
        }
        logger.debug(f'[EXTRACT] {filename} -> {result}')
        return result
