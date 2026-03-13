"""
核心刮削清洗引擎 (Scraper Cleaner)

架构说明：
- MediaCleaner 是无状态的「苦力」，本身不硬编码任何正则
- 所有正则规则来自数据库 filename_clean_regex 字段（config.json）
- 首次启动由 db_manager._inject_ai_defaults() 注入 15 条工业默认规则
- 用户可通过前端 RegexLab 自由增删，保存后立即生效
- 一键重置可从 db_manager.reset_settings_to_defaults('regex') 恢复默认

核心方法：
- clean_name(filename)            → 过滤噪声，返回纯净片名
- extract_year(filename)          → 提取年份
- extract_season_episode(filename) → 提取季/集
- clean_and_extract(filename)     → 一站式处理
"""
import re
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger(__name__)


# ============================================================
# 年份 / 季集提取正则（结构化提取，固定不变，不参与过滤）
# ============================================================
_YEAR_PATTERN = re.compile(
    r'[\(\[\.\s]+(19\d{2}|20\d{2})[\)\]\.\s]+|'
    r'\b(19\d{2}|20\d{2})\b'
)

_SEASON_EPISODE_PATTERNS: List[re.Pattern] = [
    re.compile(r'[Ss](\d{1,2})[Ee](\d{1,3})'),            # S01E01
    re.compile(r'[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee](?:pisode)?[\s\._-]*(\d{1,3})', re.IGNORECASE),  # Season 1 Episode 1
    re.compile(r'(\d{1,2})x(\d{1,3})'),                    # 1x01
    re.compile(r'[Ee][Pp]?[\s\._-]*(\d{1,3})'),            # EP01 / E01
    re.compile(r'第[\s\._-]*(\d{1,3})[\s\._-]*[集话話]'),   # 第01集
]

_ANIME_EPISODE_PATTERN = re.compile(r'[-\s](\d{2,4})(?=\s*\[)')  # - 28 [Baha]

_EXTENSION_PATTERN = re.compile(
    r'\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|mpg|mpeg|ts|m2ts|iso|rmvb|rm)$',
    re.IGNORECASE
)

_SYMBOL_CLEANUP = re.compile(r'[_\.\-\+]+')
_COLON_PATTERN = re.compile(r'[\uff1a]')

# 广告关键词（用于 is_advertisement 的快速判断）
_AD_KEYWORDS = [
    '澳门首家', '最新地址', '更多资源', '高清下载',
    '在线观看', '免费下载', 'BT下载', '磁力链接',
    '精彩推荐', '更多精彩', 'Sample', 'Trailer'
]


class MediaCleaner:
    """媒体文件名清洗器 —— 纯苦力，正则全部来自数据库"""

    def __init__(self, db_manager=None):
        """
        初始化清洗器

        Args:
            db_manager: DatabaseManager 实例，用于读取 filename_clean_regex。
                        为 None 时 clean_name() 仍可工作，但只执行符号清理。
        """
        self._db = db_manager
        self._filter_patterns: List[re.Pattern] = []
        self._loaded = False
        if db_manager is not None:
            self._load_patterns()

    # ------------------------------------------------------------------
    # 内部：从数据库加载过滤正则
    # ------------------------------------------------------------------
    def _load_patterns(self):
        """从 db_manager 读取 filename_clean_regex，编译为 pattern 列表"""
        self._filter_patterns = []
        try:
            raw = self._db.get_config('filename_clean_regex', '').strip()
            count = 0
            for line in raw.splitlines():
                rule = line.strip()
                if not rule or rule.startswith('#'):
                    continue
                try:
                    self._filter_patterns.append(re.compile(rule, re.IGNORECASE))
                    count += 1
                except re.error as e:
                    logger.warning(f'[CLEAN] 正则编译失败，已跳过: {rule[:60]} | {e}')
            logger.debug(f'[CLEAN] 已加载 {count} 条过滤规则')
            self._loaded = True
        except Exception as e:
            logger.warning(f'[CLEAN] 读取正则规则失败: {e}')

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def clean_name(self, filename: str) -> str:
        """
        剥离所有噪声标签，返回最纯净的片名

        流程：
        1. 去除文件扩展名
        2. 去除首部方括号组名（[HbT]、[SubsPlease] 等）
        3. 依次执行数据库中的过滤正则
        4. 符号清理（_.— → 空格）、首尾修整
        """
        if not filename:
            return ''

        cleaned = filename

        # 1. 去扩展名
        cleaned = _EXTENSION_PATTERN.sub('', cleaned)

        # 2. 去首部任意方括号组名（20字以内，如 [HbT]、[DBD-Raws]）
        cleaned = re.sub(r'^\s*\[[^\]]{1,20}\]\s*', '', cleaned)

        # 3. 去除剩余所有方括号及其内容（兜底）
        cleaned = re.sub(r'\[[^\]]*\]', ' ', cleaned)

        # 4. 执行数据库过滤正则
        for pat in self._filter_patterns:
            cleaned = pat.sub(' ', cleaned)

        # 4.5 剧集截断：在 S0xE0x / 1x01 处截断，只保留前面的剧名
        # 例：'The Boys S03E01 The Payback 2160p' → 'The Boys'
        # 这样可以避免 AI 把剧集标题当作额外的搜索词产生幻觉
        se_match = re.search(
            r'\b(?:[Ss]\d{1,2}[Ee]\d{1,3}|\d{1,2}x\d{1,3})\b',
            cleaned
        )
        if se_match:
            before = cleaned[:se_match.start()].strip()
            if before:  # 截断后若仍有内容则保留，否则不截断
                cleaned = before

        # 5. 中文冒号 → 英文冒号
        cleaned = _COLON_PATTERN.sub(':', cleaned)

        # 6. 下划线/点/横线 → 空格
        cleaned = _SYMBOL_CLEANUP.sub(' ', cleaned)

        # 7. 清理多余空格 & 首尾特殊符号
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        cleaned = cleaned.strip('.-_[]{}() ')

        logger.debug(f'[CLEAN] {filename} -> {cleaned}')
        return cleaned

    def extract_year(self, filename: str) -> Optional[int]:
        """从文件名提取年份"""
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
        """从文件名提取季/集号"""
        if not filename:
            return (None, None)

        for pattern in _SEASON_EPISODE_PATTERNS:
            match = pattern.search(filename)
            if match:
                groups = match.groups()
                try:
                    if len(groups) == 2:
                        return (int(groups[0]), int(groups[1]))
                    elif len(groups) == 1:
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
        """判断是否为剧集（包含季/集信息即为剧集）"""
        season, episode = self.extract_season_episode(filename)
        return season is not None or episode is not None

    def is_advertisement(self, filename: str) -> bool:
        """判断是否为纯广告/垃圾文件"""
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
        """
        净化即将用于创建文件夹/文件名的字符串（中英双语智能冒号适配）

        - 含中文：冒号替换为全角冒号 ：
        - 纯英文：冒号替换为 " - "（Plex/Jellyfin 推荐规范）
        - Windows 非法字符 < > " / \\ | ? * 替换为空格
        - 去除多余连续空格，strip
        """
        if not name:
            return ''

        # 1. 检测是否包含中文字符
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', name))

        # 2. 智能替换冒号
        if has_chinese:
            # 中文名：各种冒号 → 全角冒号 ：
            name = re.sub(r'[:\uf03a\ua789\uff1a]', '：', name)
        else:
            # 英文名：各种冒号（含全角）→ " - "
            name = re.sub(r'[:\uf03a\ua789\uff1a]', ' - ', name)

        # 3. 替换 Windows 非法字符为空格
        name = re.sub(r'[<>"/\\|?*]', ' ', name)

        # 4. 压缩连续空格并去除首尾空格
        name = re.sub(r' +', ' ', name).strip()

        return name

    def clean_and_extract(self, filename: str) -> dict:
        """
        一站式处理：清洗 + 提取所有结构化信息

        Returns:
            {
                'clean_name': str,
                'year': int | None,
                'season': int | None,
                'episode': int | None,
                'is_tv': bool,
                'is_ad': bool
            }
        """
        clean_name = self.clean_name(filename)
        year = self.extract_year(filename)
        season, episode = self.extract_season_episode(filename)
        is_tv = season is not None or episode is not None
        is_ad = self.is_advertisement(filename)

        result = {
            'clean_name': clean_name,
            'year': year,
            'season': season,
            'episode': episode,
            'is_tv': is_tv,
            'is_ad': is_ad
        }
        logger.debug(f'[EXTRACT] {filename} -> {result}')
        return result

