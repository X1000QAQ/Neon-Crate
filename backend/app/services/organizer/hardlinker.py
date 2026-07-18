"""
智能链接引擎 - 硬链接优先、软链接兜底。

职责：
- 将下载目录中的媒体文件链接到媒体库目标路径。
- 优先创建硬链接，实现零拷贝归档并保留做种能力。
- 跨分区时自动回退为软链接，避免物理复制占用额外空间。
- 同步同目录字幕文件，保持视频和字幕侧车文件一致。

调用边界：
- 本模块只处理文件系统链接，不写数据库、不生成 NFO、不访问 TMDB。
- 上游负责计算目标路径、校验媒体类型和更新任务状态。
"""
import os
import errno
import logging
from pathlib import Path
from typing import Tuple
from app.infra.constants import SUB_EXTS, SUB_LANG_SUFFIXES

logger = logging.getLogger(__name__)


# 静态调用说明：本类所有方法均为 @staticmethod，调用方式为 SmartLink.create_link(...)。
# GitNexus 等 AST 静态分析工具可能无法识别此类调用边，图谱中的 incoming 为空时可能是误报。
# 修改本类任何方法签名前，请先用代码搜索手动确认所有调用点。
class SmartLink:
    """
    智能链接工具。

    提供硬链接、软链接兜底、链接类型检测和字幕同步能力。
    所有方法均为静态方法，调用方无需实例化。
    """
    
    @staticmethod
    def create_link(src: str, dst: str) -> Tuple[bool, str]:
        """
        创建智能链接（硬链接优先，跨盘自动回退到软链接）
        
        设计理念：
        - 硬链接优先：零空间占用，性能最优，保持做种
        - 智能兜底：跨分区时自动切换为软链接
        - 幂等处理：目标文件已存在时视为成功
        
        硬链接 vs 软链接：
        - 硬链接：共享 inode，删除源文件不影响目标文件，适合做种
        - 软链接：类似快捷方式，删除源文件会导致目标文件失效
        
        跨分区检测：
        - 错误码：errno.EXDEV（Cross-device link）
        - 触发场景：源文件和目标文件在不同的文件系统
        - 自动回退：检测到跨分区错误时自动使用软链接
        
        Args:
            src: 源文件路径（必须存在）
            dst: 目标文件路径（不能存在）
        
        Returns:
            Tuple[bool, str]: (是否成功, 链接类型或错误信息)
        
        链接类型：
            - "hardlink": 硬链接成功
            - "symlink": 软链接成功（跨分区兜底）
            - "already_exists": 目标文件已存在（幂等处理）
            - "error: xxx": 失败原因
        """
        # 前置检查
        if not os.path.exists(src):
            error_msg = f"源文件不存在: {src}"
            logger.error(f"[ORG] {error_msg}")
            return False, f"error: {error_msg}"
        
        if os.path.exists(dst):
            # 目标文件已存在，视为已归档成功（幂等处理）
            logger.info(f"[ORG] 目标文件已存在，视为已归档: {dst}")
            return True, "already_exists"
        
        # 确保目标目录存在
        dst_dir = os.path.dirname(dst)
        try:
            os.makedirs(dst_dir, exist_ok=True)
        except Exception as e:
            error_msg = f"创建目标目录失败: {e}"
            logger.error(f"[ORG] {error_msg}")
            return False, f"error: {error_msg}"
        
        # 尝试硬链接
        try:
            os.link(src, dst)
            logger.info(f"[ORG] Hardlink created: {src} -> {dst}")
            return True, "hardlink"
        except OSError as e:
            # 检查是否是跨分区错误
            if e.errno == errno.EXDEV:
                logger.warning(f"[ORG] Cross-disk detected, fallback to Symlink: {src} -> {dst}")
                
                # 回退到软链接
                try:
                    # Windows 特性：需要指定 target_is_directory 参数
                    is_dir = os.path.isdir(src)
                    
                    if os.name == 'nt':  # Windows
                        os.symlink(src, dst, target_is_directory=is_dir)
                    else:  # Linux/macOS
                        os.symlink(src, dst)
                    
                    logger.info(f"[ORG] Symlink created (cross-disk fallback): {src} -> {dst}")
                    return True, "symlink"
                except Exception as symlink_error:
                    error_msg = f"软链接创建失败: {symlink_error}"
                    logger.error(f"[ORG] {error_msg}")
                    return False, f"error: {error_msg}"
            else:
                # 其他错误
                error_msg = f"硬链接创建失败: {e}"
                logger.error(f"[ORG] {error_msg}")
                return False, f"error: {error_msg}"
    
    @staticmethod
    def create_link_safe(src: str, dst: str) -> bool:
        """
        创建智能链接（简化版，仅返回成功/失败）
        
        Args:
            src: 源文件路径
            dst: 目标文件路径
        
        Returns:
            bool: 是否成功
        """
        success, link_type = SmartLink.create_link(src, dst)
        return success
    
    @staticmethod
    def get_link_type(path: str) -> str:
        """
        检测文件的链接类型
        
        Args:
            path: 文件路径
        
        Returns:
            str: "hardlink" | "symlink" | "regular" | "not_exist"
        """
        if not os.path.exists(path):
            return "not_exist"
        
        # 检查是否是软链接
        if os.path.islink(path):
            return "symlink"
        
        # 检查是否是硬链接（通过 inode 引用计数）
        try:
            stat_info = os.stat(path)
            if stat_info.st_nlink > 1:
                return "hardlink"
        except:
            pass
        
        return "regular"
    
    @staticmethod
    def sync_subtitles(src_video_path: str, dest_video_path: str, dest_dir: str) -> int:
        """
        自带字幕全量搬运（智能同步机制）
        
        设计目标：
        - 将源视频同目录下的字幕文件同步到目标目录
        - 支持多语言字幕（.zh-cn.srt、.en.srt 等）
        - 防止交叉污染（只搬运与源视频同名的字幕）
        
        平铺目录检测：
        - 问题场景：下载目录中混放了多部影片，每部影片都有自己的字幕
        - 检测策略：
          1. 公共大厅识别：downloads、movie、tv 等常见目录名
          2. 异类嗅探：同目录下有不同前缀的视频文件
        - 防护措施：检测到平铺目录时跳过字幕扫描，避免误搬运
        
        前缀匹配防交叉污染：
        - 只搬运文件名以源视频 stem 开头的字幕
        - 例如：The.Matrix.1999.mkv 只搬运 The.Matrix.1999.*.srt
        - 避免：The.Matrix.2.mkv 的字幕被误搬运到 The.Matrix.1.mkv
        
        Args:
            src_video_path: 源视频路径
            dest_video_path: 目标视频路径
            dest_dir: 目标目录
        
        Returns:
            成功搬运的字幕数量
        """
        # 平铺目录检测
        try:
            if SmartLink._is_flat_directory(Path(src_video_path)):
                logger.warning("[ORG] 检测到平铺目录，跳过字幕扫描")
                return 0
        except Exception as e:
            logger.warning(f"[ORG] 平铺目录嗅探异常，跳过字幕扫描: {e}")
            return 0
        
        src_dir = os.path.dirname(os.path.normpath(src_video_path))
        src_stem = Path(src_video_path).stem.lower()
        dest_stem = Path(dest_video_path).stem
        linked_count = 0
        
        try:
            src_path = Path(src_dir)
            if not src_path.exists() or not src_path.is_dir():
                return 0
            
            collected = []
            for p in src_path.rglob("*"):
                if not p.is_file():
                    continue
                if p.suffix.lower() not in SUB_EXTS:
                    continue
                # 前缀匹配防交叉污染
                if not p.name.lower().startswith(src_stem):
                    continue
                collected.append(p)
            
            for sub_path in collected:
                full_suffix = SmartLink._normalized_subtitle_suffix(sub_path)
                new_name = dest_stem + full_suffix
                dest_sub = os.path.join(dest_dir, new_name)
                
                success, _ = SmartLink.create_link(str(sub_path), dest_sub)
                if success:
                    linked_count += 1
                    logger.info(f"[ORG] 自带字幕已同步: {new_name}")
        
        except Exception as e:
            logger.warning(f"[ORG] 自带字幕同步异常: {e}")
        
        return linked_count
    
    @staticmethod
    def _is_flat_directory(video_path: Path) -> bool:
        """
        平铺目录嗅探器（增强版）

        规则 A：路径深度检测 — 距根锚 ≤3 层（如 /downloads/movie.mkv）视为平铺目录
        规则 B：异类嗅探增强 — 提取主片名（去年份/分辨率后缀）再比较，
                同目录中出现 2 个以上不同主片名的视频文件即判定为平铺目录
        """
        parent = video_path.parent
        try:
            if not parent.exists() or not parent.is_dir():
                return False
        except Exception:
            return False

        # 规则 A：路径深度检测
        try:
            depth = len(video_path.relative_to(video_path.anchor).parts)
            if depth <= 3:
                return True
        except Exception:
            pass

        # 规则 B：异类嗅探增强版
        def _extract_stem(name: str) -> str:
            s = re.sub(r'\.(19|20)\d{2}\..*', '', name.lower())
            s = re.sub(r'\.(720p|1080p|2160p|4k|bluray|webrip|hdtv).*', '', s)
            return s.strip()

        current_stem = _extract_stem(video_path.stem)
        video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".ts", ".flv"}

        try:
            siblings = [
                c for c in parent.iterdir()
                if c.is_file() and c.suffix.lower() in video_exts and c != video_path
            ]
            different_stems: set = set()
            for sibling in siblings[:5]:
                sib_stem = _extract_stem(sibling.stem)
                if sib_stem and sib_stem != current_stem:
                    different_stems.add(sib_stem)
                if len(different_stems) >= 2:
                    return True
        except Exception:
            pass

        return False
    
    @staticmethod
    def _normalized_subtitle_suffix(sub_path: Path) -> str:
        """提取语言.扩展名部分"""
        suffixes = sub_path.suffixes
        if not suffixes:
            return ".srt"
        
        ext = suffixes[-1].lower()
        if ext not in SUB_EXTS:
            ext = ".srt"
        
        if len(suffixes) >= 2 and suffixes[-2].lower() in SUB_LANG_SUFFIXES:
            return suffixes[-2] + suffixes[-1]
        
        return ext
