"""
app/infra/constants.py - 全局常量大本营

设计规则：
- 本文件不得导入任何 app 内部模块
- 仅使用 Python 内置类型（frozenset / tuple）
- 所有其他模块统一从此处导入常量，禁止在业务代码中散落定义

常量分层：
- VIDEO_EXTS：核心视频格式（搬运/字幕同步，较保守）
- VIDEO_EXTS_EXTENDED：扫描引擎专用（包含更多网络视频格式）
- SUB_EXTS：字幕同步格式（搬运时使用）
- VALID_SUB_EXTS：完整字幕格式（本地检测/下载验证，最宽泛）
- SUB_LANG_SUFFIXES：字幕语言后缀（用于多语言字幕识别）
"""

# ── 视频扩展名（分层定义）──────────────────────────────────────

# 核心视频格式（搬运/字幕同步使用，较保守）
VIDEO_EXTS = frozenset({
    ".mkv", ".mp4", ".avi", ".mov",
    ".wmv", ".ts", ".flv", ".m2ts"
})

# 扩展视频格式（扫描引擎专用，包含更多网络视频格式）
# ⚠️ 注意：scraper/engine.py 故意包含 .webm/.m4v/.mpg/.mpeg，不能与 VIDEO_EXTS 混用
VIDEO_EXTS_EXTENDED = frozenset({
    ".mkv", ".mp4", ".avi", ".mov", ".wmv",
    ".ts", ".flv", ".m2ts",
    ".webm", ".m4v", ".mpg", ".mpeg",  # 扫描引擎专用，支持更多网络视频格式
    ".rmvb", ".iso", ".vob"            # 历史兜底扩展名：兼容旧版扫描/清理范围
})

# ── 字幕扩展名（分用途定义）─────────────────────────────────────

# 字幕同步格式（搬运时使用，不含 Web 格式和 DVD 格式）
SUB_EXTS = frozenset({".srt", ".ass", ".ssa", ".sub"})

# 完整字幕格式（本地检测/下载验证使用，最宽泛）
VALID_SUB_EXTS = frozenset({".srt", ".ass", ".ssa", ".vtt", ".sub", ".idx"})

# ── 字幕语言后缀 ──────────────────────────────────────────────
# 用于识别多语言字幕文件名中的语言代码部分
# 例如：The.Matrix.1999.zh-cn.srt → 语言后缀为 .zh-cn
SUB_LANG_SUFFIXES = frozenset({
    ".zh-cn", ".zh", ".chs", ".chi", ".zh-tw", ".zh-hk"
})
