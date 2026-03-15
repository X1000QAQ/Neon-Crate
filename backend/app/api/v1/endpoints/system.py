"""
系统监控端点 - System API

功能说明：
1. 系统统计：提供控制台大屏数据
2. 日志查询：支持按标签过滤的日志查询
3. 图片代理：安全的图片访问代理

核心特性：
- 缓存模式：媒体库统计使用缓存，避免频繁 I/O
- 日志过滤：支持按 SCAN、TMDB、ERROR 等标签过滤
- 路径防御：防止路径穿越攻击，保护系统敏感目录

图片代理安全机制：
1. 路径穿越防御：使用 Path.resolve() 处理 ../
2. 动态黑名单：根据操作系统自适应敏感目录
3. 后缀名校验：只允许图片格式（jpg、png、webp 等）
4. 存在性检查：确保文件存在且可读

日志解析：
- 标准格式：时间戳 - 模块 - 级别 - 消息
- 非标准格式：兼容 print 输出，作为 INFO 级别保留
- 时间戳格式化：ISO 8601 标准（T 分隔符，点号毫秒）
"""
import logging
import platform
import re
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse

from app.api.v1.deps import DbDep
from app.models.domain_media import StatsResponse

router = APIRouter()
public_router = APIRouter()

# 日志文件路径 - 自适应路径（支持 Windows 和 Docker）
# system.py 位于 app/api/v1/endpoints/system.py，需要 5 层 parent 到达项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
APP_LOG_PATH = BASE_DIR / "data" / "logs" / "app.log"
# 确保日志目录存在
APP_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

VALID_TAGS = {"SCAN", "TMDB", "SUBTITLE", "ERROR", "API", "ORGANIZER", "ORG", "CLEAN", "LLM", "AI", "AI-EXEC", "META", "DB", "SECURITY", "DEBUG"}


def _last_n_lines_reverse(path: Path, n: int = 1000) -> List[str]:
    """
    从文件末尾反向读取最后 n 行（高效大文件读取）
    
    设计目标：
    - 避免将整个日志文件加载到内存
    - 从文件末尾分块读取，性能高效
    - 支持 UTF-8 编码，容错处理编码错误
    
    分块读取策略：
    - 块大小：64KB（适合大多数日志场景）
    - 从文件末尾向前读取，直到收集够 n 行
    - 跨块的行自动拼接，不会截断
    
    Args:
        path: 日志文件路径
        n: 读取的最大行数（默认 1000）
    
    Returns:
        List[str]: 最后 n 行的列表（顺序从旧到新）
    """
    if not path.exists() or not path.is_file():
        return []
    try:
        chunk_size = 64 * 1024
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            lines = []
            pos = size
            while pos > 0 and len(lines) < n:
                read_size = min(chunk_size, pos)
                pos -= read_size
                f.seek(pos)
                chunk = f.read(read_size).decode("utf-8", errors="replace")
                parts = chunk.splitlines()
                if lines and parts:
                    lines[0] = parts[-1] + lines[0]
                    parts = parts[:-1]
                lines = parts + lines
            return lines[-n:] if len(lines) > n else lines
    except Exception:
        return []


def _parse_log_line(line: str) -> dict:
    """
    解析单行日志（兼容标准格式和非标准格式）
    
    标准格式：2026-03-09 12:34:56,789 - app.module - INFO - [TAG] message
    非标准格式：任意文本（如 print 输出）
    
    改进点：
    - 如果不符合标准正则，不丢弃，而是作为 INFO 级别保留
    - 尝试从文本中提取 [SCAN]、[API] 等标签
    - 时间戳格式化为 ISO 8601（空格替换为 T，逗号替换为点号）
    """
    # 先尝试提取标签
    tag = None
    for t in VALID_TAGS:
        if f"[{t}]" in line.upper():
            tag = t
            break
    
    # 尝试匹配标准日志格式
    log_pattern = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+-\s+\S+\s+-\s+(INFO|WARNING|ERROR|DEBUG)\s+-\s+(.+)$"
    )
    match = log_pattern.match(line.strip())
    if match:
        ts, level, msg = match.groups()
        # 关键修复：将空格替换为 T，逗号替换为点号，符合 ISO 8601 标准
        ts = ts.replace(" ", "T").replace(",", ".")
        return {"raw": line, "timestamp": ts, "level": level, "message": msg, "tag": tag}
    
    # 不符合标准格式，作为 INFO 级别保留（兼容 print 输出）
    return {"raw": line, "timestamp": None, "level": "INFO", "message": line.strip(), "tag": tag}


@public_router.get("/image")
async def proxy_image(path: str = Query(..., description="绝对图片物理路径（URL 编码）")):
    """
    图片代理：
    - 自适应 Windows / Linux (Unraid) 环境
    - 使用 Path.resolve() 防御 ../ 路径穿越
    - 基于当前操作系统动态维护敏感目录黑名单
    """
    import urllib.parse

    logger = logging.getLogger(__name__)

    # 1. 基础清理与绝对路径转换（保持 UTF-8 语义不变）
    try:
        decoded_path = urllib.parse.unquote(path)  # 前端 encodeURIComponent 对应解码
    except Exception:
        raise HTTPException(status_code=400, detail="非法的路径编码格式")

    clean_path_str = decoded_path.replace("\\", "/").strip()
    if not clean_path_str:
        raise HTTPException(status_code=400, detail="非法的路径格式")

    try:
        # resolve() 会处理掉所有的 ../ 等路径穿越尝试
        img_path = Path(clean_path_str).resolve(strict=False)
    except Exception:
        raise HTTPException(status_code=400, detail="非法的路径格式")

    # 额外的 normpath 规范化（处理重复斜杠等边缘情况）
    import os
    img_path = Path(os.path.normpath(str(img_path)))

    # ── 手术三：白名单锚定（合法媒体库路径严苛校验）────────────────────────
    # 优先于黑名单执行：请求的文件必须是已配置的媒体库或下载目录的子文件
    try:
        from app.infra.database import get_db_manager as _get_db
        _db = _get_db()
        _managed = _db.get_managed_paths()
        allowed_paths = [
            Path(p["path"]).resolve()
            for p in _managed
            if p.get("path") and p.get("enabled", True)
        ]

        # 🚀 动态扩容：追加 Docker 挂载点和本地开发数据目录
        extra_allowed = []

        # Docker 挂载点（/storage 等）
        docker_storage = Path("/storage")
        if docker_storage.exists():
            extra_allowed.append(docker_storage.resolve())

        # 本地数据目录（data/posters 等）
        local_data = BASE_DIR / "data"
        if local_data.exists():
            extra_allowed.append(local_data.resolve())

        # 本地开发兼容：允许访问 /home 下的本地资源目录（开发环境）
        import os
        from app.infra.config import settings as _settings
        dev_mode = _settings.APP_ENV.lower() in ("development", "dev", "local")
        if dev_mode:
            home_path = Path.home()
            extra_allowed.append(home_path.resolve())
            logger.debug(f"[SECURITY] 开发模式：已追加 home 目录至白名单: {home_path}")

        all_allowed = allowed_paths + extra_allowed

        if all_allowed:
            is_allowed = any(
                str(img_path).startswith(str(allowed))
                for allowed in all_allowed
            )
            if not is_allowed:
                logger.error(f"❌ [SECURITY_DENIED] 访问被拒！请求路径: {img_path} | 规范化后: {img_path.resolve()} | 当前白名单: {[str(p) for p in all_allowed]}")
                raise HTTPException(status_code=403, detail="Forbidden: Path not in managed media directories")
    except HTTPException:
        raise
    except Exception as wl_err:
        # 白名单读取失败时降级到黑名单（不阻断服务）
        logger.warning(f"[SECURITY] 白名单读取失败，降级到黑名单模式: {wl_err}")

    # 2. 动态黑名单库（按当前 OS 自适应）
    current_os = platform.system()
    if current_os == "Windows":
        banned_prefixes = [
            "C:/Windows",
            "C:/Users",
            "C:/Program Files",
        ]
    else:
        banned_prefixes = [
            "/etc",
            "/root",
            "/boot",
            "/proc",
            "/sys",
            "/dev",
            "/var/run",
        ]

    # 3. 智能防御校验：使用标准 POSIX 形式做前缀比对
    normalized_path = img_path.as_posix()
    lower_normalized_path = normalized_path.lower()
    for prefix in banned_prefixes:
        if lower_normalized_path.startswith(prefix.lower()):
            logger.warning(f"[IMAGE_PROXY_SECURITY] 拦截到敏感路径访问尝试: {normalized_path} (os={current_os})")
            raise HTTPException(status_code=403, detail="安全拦截：禁止访问系统敏感目录")

    # 路径层级审计（不过度限制 D:/ 等媒体盘直链，记录审计）
    parts = img_path.parts
    if len(parts) <= 2:
        logger.info(f"[IMAGE_PROXY_SECURITY] 路径层级较浅，已放行但记录审计: {normalized_path} (parts={parts})")

    # 4. 后缀名与存在性校验（保留上一轮逻辑）
    VALID_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    if img_path.suffix.lower() not in VALID_IMAGE_SUFFIXES:
        logger.warning(
            f"[IMAGE_PROXY_SECURITY] 触发 403 拦截，非授权图片后缀访问尝试：suffix={img_path.suffix}, path={normalized_path}"
        )
        raise HTTPException(
            status_code=403,
            detail=f"安全拦截：不允许访问非图片格式文件 ({img_path.suffix})",
        )

    if not img_path.exists() or not img_path.is_file():
        logger.error(f"[IMAGE_PROXY_DEBUG] 触发 404 拦截！文件不存在: {normalized_path}")
        raise HTTPException(status_code=404, detail="图片在物理磁盘上不存在")

    logger.info(f"[IMAGE_ACCESS_SUCCESS] ✅ 图片代理成功: {normalized_path}")
    return FileResponse(str(img_path))


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: DbDep):
    """
    获取控制台大屏统计数据（缓存模式）

    movies / tv_shows 从数据库缓存读取，仅在扫描/刮削任务完成后更新。
    不实时扫描硬盘，避免对 NAS 造成频繁 I/O 压力。

    缓存更新时机：
    - 手动点击扫描/刮削按钮
    - AI 意图触发扫描/刮削
    - 定时巡逻完成刮削步骤
    """
    # 从数据库读取由刮削任务写入的缓存计数
    movie_count = int(db.get_config("library_movies_count", 0) or 0)
    tv_count    = int(db.get_config("library_tv_count",    0) or 0)

    # 流水线实时统计（只读 tasks 表，无 I/O 压力）
    stats = db.get_dashboard_stats()

    return StatsResponse(
        movies=movie_count,
        tv_shows=tv_count,
        pending=int(stats.get("pending",   0) or 0),
        completed=int(stats.get("completed", 0) or 0)
    )


@router.get("/logs")
async def get_logs(
    tags: Optional[str] = Query(None, description="逗号分隔的标签过滤，如 SCAN,TMDB,SUBTITLE,ERROR,API")
):
    """
    读取系统日志（最后 1000 行）
    
    支持按标签过滤：SCAN, TMDB, SUBTITLE, ERROR, API, ORGANIZER
    
    Args:
        tags: 逗号分隔的标签列表
        
    Returns:
        日志条目列表
    """
    if not APP_LOG_PATH.exists():
        return {"logs": [], "source": str(APP_LOG_PATH), "message": "日志文件不存在"}
    
    raw_lines = _last_n_lines_reverse(APP_LOG_PATH, 1000)
    parsed = [_parse_log_line(ln) for ln in raw_lines if ln.strip()]
    
    # 标签过滤
    if tags and tags.strip():
        allowed = {t.strip().upper() for t in tags.split(",") if t.strip()}
        allowed &= VALID_TAGS
        if allowed:
            parsed = [p for p in parsed if p.get("tag") in allowed]
    
    from datetime import datetime
    import hashlib
    result = []
    for idx, p in enumerate(parsed):
        ts = p["timestamp"]
        if ts:
            try:
                ts = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S,%f").isoformat()
            except Exception:
                pass
        
        # 生成唯一 ID（timestamp + line_hash）防止 React Key 冲突
        raw_content = p.get("raw", "")
        line_hash = hashlib.md5(raw_content.encode()).hexdigest()[:8]
        unique_id = f"{ts or idx}-{line_hash}"
        
        result.append({
            "id": unique_id,
            "timestamp": ts or "",
            "level": (p["level"] or "INFO").upper(),
            "message": p["message"] or p["raw"],
            "tag": p.get("tag"),
        })
    
    return {"logs": result, "source": str(APP_LOG_PATH), "total": len(result)}
