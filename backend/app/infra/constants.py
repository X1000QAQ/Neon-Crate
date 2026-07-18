"""
全局常量模块 - 视频、字幕扩展名与语言后缀

职责：
- 集中定义后端多个模块共享的静态常量。
- 保证扫描、归档、字幕同步、字幕验证使用同一套扩展名口径。
- 避免业务代码中散落重复的扩展名列表。

常量分层：
- `VIDEO_EXTS`：归档和字幕同步使用的核心视频格式，范围较保守。
- `VIDEO_EXTS_EXTENDED`：扫描引擎使用的扩展视频格式，包含更多网络视频和历史格式。
- `SUB_EXTS`：搬运时同步字幕使用的基础字幕格式。
- `VALID_SUB_EXTS`：字幕检测和下载验证使用的完整字幕格式。
- `SUB_LANG_SUFFIXES`：用于识别 `.zh-cn.srt` 等多语言字幕后缀。

与配置项的关系：
- 运行时可通过数据库配置 `supported_video_exts` / `supported_subtitle_exts` 覆盖部分格式范围。
- 本文件提供静态兜底值，数据库读取失败或配置为空时由业务模块回退使用。
- 本文件不得导入任何 `app` 内部模块，避免基础常量形成循环依赖。
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
