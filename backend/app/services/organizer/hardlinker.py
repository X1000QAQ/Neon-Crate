"""
智能链接引擎 - SmartLink

核心特性：
1. 首选硬链接（os.link）：零空间占用，性能最优
2. 智能兜底（os.symlink）：跨分区时自动切换为软链接
3. Windows 特性适配：自动处理 target_is_directory 参数
4. 完整日志审计：记录每次链接操作的类型和结果
5. 字幕同步：自动搬运同目录字幕文件

使用场景：
- 媒体库归档：将下载目录的文件链接到媒体库
- 跨盘归档：自动检测跨分区错误并回退到软链接
- 零拷贝迁移：避免物理复制，节省磁盘空间
"""
import os
import errno
import logging
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)

# 字幕扩展名
SUB_EXTS = (".srt", ".ass", ".ssa", ".sub")
SUB_LANG_SUFFIXES = (".zh-cn", ".zh", ".chs", ".chi", ".zh-tw", ".zh-hk")


class SmartLink:
    """智能链接引擎"""
    
    @staticmethod
    def create_link(src: str, dst: str) -> Tuple[bool, str]:
        """
        创建智能链接（硬链接优先，跨盘自动回退到软链接）
        
        Args:
            src: 源文件路径（必须存在）
            dst: 目标文件路径（不能存在）
        
        Returns:
            Tuple[bool, str]: (是否成功, 链接类型或错误信息)
        
        链接类型：
            - "hardlink": 硬链接成功
            - "symlink": 软链接成功（跨分区兜底）
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
        自带字幕全量搬运
        
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
        """平铺目录嗅探器"""
        parent = video_path.parent
        try:
            if not parent.exists() or not parent.is_dir():
                return False
        except Exception:
            return False
        
        dir_name = parent.name.strip().lower()
        common_hall_names = {"downloads", "movie", "tv", "completed", "pt"}
        
        # 规则 A：公共大厅识别
        if dir_name in common_hall_names:
            return True
        
        # 规则 B：异类嗅探
        current_prefix = video_path.name.lower()[:3]
        video_exts = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".ts", ".flv"}
        
        try:
            for child in parent.iterdir():
                if not child.is_file():
                    continue
                if child == video_path:
                    continue
                if child.suffix.lower() not in video_exts:
                    continue
                other_prefix = child.name.lower()[:3]
                if other_prefix and other_prefix != current_prefix:
                    return True
        except Exception:
            return False
        
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
