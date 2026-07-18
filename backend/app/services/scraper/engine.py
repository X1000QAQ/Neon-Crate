"""
并发扫描引擎 - 视频文件发现、物理过滤与上下文采集。

职责：
- 根据配置的视频扩展名和最小体积限制发现候选视频文件。
- 使用路径集合和 inode 指纹对已入库文件做前置去重。
- 采集父目录与同级文件名样本，为后续 AI 语义识别提供上下文。
- 使用线程池并发处理文件，降低大目录扫描耗时。

边界：
- 扫描阶段不判断真实片名、年份、电影 / 剧集类型或季集语义。
- `clean_name/year/is_tv/season/episode` 仅作为兼容字段返回空值，实际解析由刮削阶段 AI 链路完成。
- 正则仅用于样片、隐藏目录和固定路径形态过滤，不恢复用户自定义文件名清洗规则。

安全与稳定性：
- `followlinks=False` 防止软链接循环。
- `MAX_SCAN_DEPTH` 限制递归深度，避免恶意或异常目录结构拖垮扫描任务。
"""
import os
import re
from pathlib import Path
from typing import List, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .filters import MediaFilter
from app.infra.constants import VIDEO_EXTS_EXTENDED

logger = logging.getLogger(__name__)


def _parse_ext_config(raw: str) -> frozenset:
    """将逗号分隔的后缀字符串解析为小写 frozenset，去除多余空格。"""
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    # 确保每个后缀以 '.' 开头
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts)


class ScanEngine:
    """
    并发扫描引擎。

    本类只负责文件系统层面的“发现与过滤”：
    - 视频扩展名过滤。
    - 最小体积过滤。
    - 样片 / 隐藏目录剪枝。
    - 路径和 inode 防重。
    - 同级文件上下文采集。

    不负责：
    - 影视名称语义清洗。
    - TMDB 搜索。
    - NFO / 海报写入。
    - 文件移动或硬链接归档。
    """

    # 静态兜底（db 读取失败时使用）
    _VIDEO_EXTS_FALLBACK = VIDEO_EXTS_EXTENDED

    def __init__(self, max_workers: int = 4, min_size_mb: int = 50, db_manager=None, known_paths: set = None, known_inodes: set = None):
        """
        初始化扫描引擎
        
        Args:
            max_workers: 最大并发线程数
            min_size_mb: 最小文件体积限制（MB）
            db_manager: 数据库管理器（用于读取视频扩展名配置）
            known_paths: 已入库文件路径集合（用于前置过滤）
            known_inodes: 已入库文件物理指纹集合（用于硬链接防重）
        """
        self.max_workers = max_workers
        self.min_size_mb = min_size_mb
        self.filter = MediaFilter(min_size_mb=min_size_mb)
        self.known_paths = known_paths or set()  # 🚀 保存路径白名单
        self.known_inodes = known_inodes or set()  # 🛡️ 保存 inode 白名单
        # 动态读取视频格式（从数据库，失败时兜底静态常量）
        if db_manager is not None:
            try:
                _raw = db_manager.get_config("supported_video_exts", "")
                self.VIDEO_EXTENSIONS = _parse_ext_config(_raw) if _raw else self._VIDEO_EXTS_FALLBACK
            except Exception:
                self.VIDEO_EXTENSIONS = self._VIDEO_EXTS_FALLBACK
        else:
            self.VIDEO_EXTENSIONS = self._VIDEO_EXTS_FALLBACK
    
    def scan_directory(self, directory: str, recursive: bool = True) -> List[Dict]:
        """
        扫描目录，返回符合条件的视频文件
        
        Args:
            directory: 目标目录路径
            recursive: 是否递归扫描子目录
        
        Returns:
            视频文件列表，每个元素包含 path, file_name, size, parent_dir_path, sibling_files。
            clean_name/year/is_tv/season/episode 仅保留为空值兼容字段，解析由刮削 AI 链路负责。
        """
        if not os.path.exists(directory):
            logger.warning(f"目录不存在: {directory}")
            return []
        
        logger.info(f"开始扫描目录: {directory} (递归={recursive})")
        
        # 收集所有视频文件
        video_files = self._collect_video_files(directory, recursive)
        logger.info(f"发现 {len(video_files)} 个视频文件")
        
        # 并发过滤和上下文采集
        results = self._process_files_concurrent(video_files)
        
        logger.info(f"扫描完成，符合条件的文件: {len(results)} 个")
        return results
    
    # 递归深度上限：防止软链接死循环或恶意构造的超深目录导致栈溢出
    MAX_SCAN_DEPTH = 5

    def _collect_video_files(self, directory: str, recursive: bool) -> List[str]:
        """收集所有视频文件路径（follow_symlinks=False 防死循环，MAX_SCAN_DEPTH 限深）"""
        video_files = []
        base_depth = directory.rstrip(os.sep).count(os.sep)

        try:
            if recursive:
                # 递归扫描：follow_symlinks=False 防止软链接死循环
                for root, dirs, files in os.walk(directory, followlinks=False):
                    # ── 深度限制：超过 MAX_SCAN_DEPTH 层时剪枝，不再向下遍历 ──
                    current_depth = root.rstrip(os.sep).count(os.sep) - base_depth
                    if current_depth >= self.MAX_SCAN_DEPTH:
                        logger.warning(
                            f"[SCAN] 深度超限（{current_depth}/{self.MAX_SCAN_DEPTH}），已停止向下递归: {root}"
                        )
                        dirs.clear()  # 就地清空，os.walk 将不再进入子目录
                        continue

                    # 跳过隐藏目录和系统目录（就地修改 dirs 实现剪枝）
                    root_lower = root.lower()
                    if '/@eadir/' in root_lower or '.deletedbytmm' in root_lower or '/.' in root:
                        dirs.clear()
                        continue

                    # 跳过样片目录
                    if re.search(r'[/\\]sample\b|[/\\]样片\b', root_lower):
                        dirs.clear()
                        continue

                    for file in files:
                        # 跳过隐藏文件
                        if file.startswith('.'):
                            continue

                        # 跳过样片文件
                        if re.search(r'[-_]?\bsample\b|样片', file, flags=re.IGNORECASE):
                            continue

                        if self._is_video_file(file):
                            file_path = os.path.join(root, file)
                            
                            # 🚀 第一重拦截：路径白名单（O(1) 哈希查找）
                            if self.known_paths:
                                try:
                                    if str(Path(file_path).resolve()) in self.known_paths:
                                        continue  # 静默跳过
                                except Exception:
                                    pass  # 规范化失败时降级为不过滤
                            
                            # 🛡️ 第二重拦截：物理 inode 指纹（终极防重，蒸发做种文件）
                            if self.known_inodes:
                                try:
                                    st = os.stat(file_path)
                                    if (st.st_ino, st.st_size) in self.known_inodes:
                                        continue  # 静默跳过硬链接文件
                                except OSError:
                                    pass  # stat 失败时降级为不过滤
                            
                            video_files.append(file_path)
            else:
                # 仅扫描当前目录（非递归，无需深度检查）
                for file in os.listdir(directory):
                    file_path = os.path.join(directory, file)
                    if os.path.isfile(file_path) and self._is_video_file(file):
                        # 🚀 第一重拦截：路径白名单（O(1) 哈希查找）
                        if self.known_paths:
                            try:
                                if str(Path(file_path).resolve()) in self.known_paths:
                                    continue  # 静默跳过
                            except Exception:
                                pass
                        
                        # 🛡️ 第二重拦截：物理 inode 指纹（终极防重，蒸发做种文件）
                        if self.known_inodes:
                            try:
                                st = os.stat(file_path)
                                if (st.st_ino, st.st_size) in self.known_inodes:
                                    continue  # 静默跳过硬链接文件
                            except OSError:
                                pass
                        
                        video_files.append(file_path)
        except Exception as e:
            logger.error(f"扫描目录失败: {e}")

        return video_files
    
    def _is_video_file(self, filename: str) -> bool:
        """判断是否为视频文件"""
        ext = Path(filename).suffix.lower()
        return ext in self.VIDEO_EXTENSIONS
    
    def _process_files_concurrent(self, file_paths: List[str]) -> List[Dict]:
        """并发处理文件（物理过滤 + 上下文采集）"""
        results = []
        processed_paths: Set[str] = set()  # 去重
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交所有任务
            future_to_path = {
                executor.submit(self._process_single_file, path): path 
                for path in file_paths
            }
            
            # 收集结果
            for future in as_completed(future_to_path):
                try:
                    result = future.result()
                    if result and result['path'] not in processed_paths:
                        results.append(result)
                        processed_paths.add(result['path'])
                except Exception as e:
                    path = future_to_path[future]
                    logger.error(f"处理文件失败 {path}: {e}")
        
        return results
    
    def _process_single_file(self, file_path: str) -> Dict | None:
        """
        处理单个文件：只做物理过滤与上下文采集。

        Returns:
            符合条件的文件信息，或 None（不符合条件）
        """
        try:
            if not self.filter.check_file_size(file_path):
                return None

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            parent_path = str(Path(file_path).parent)
            sibling_files = self._collect_sibling_files(file_path)

            return {
                'path': file_path,
                'file_name': file_name,
                'size': file_size,
                'parent_dir_path': parent_path,
                'sibling_files': sibling_files,
                'clean_name': None,
                'year': None,
                'is_tv': None,
                'season': None,
                'episode': None,
            }

        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {e}")
            return None

    def _collect_sibling_files(self, file_path: str, limit: int = 40) -> List[str]:
        """采集同级视频文件名样本，供后续 AI 语义解析使用。"""
        try:
            current = Path(file_path)
            parent = current.parent
            if not parent.exists():
                return []
            siblings = [
                p.name for p in parent.iterdir()
                if p.is_file() and self._is_video_file(p.name)
            ]
            return sorted(siblings)[:limit]
        except Exception as e:
            logger.debug(f"[SCAN] 同级文件上下文采集失败: {file_path} | {e}")
            return []
    
    def scan_multiple_directories(self, directories: List[str]) -> List[Dict]:
        """
        批量扫描多个目录
        
        Args:
            directories: 目录路径列表
        
        Returns:
            合并后的视频文件列表
        """
        all_results = []
        processed_paths: Set[str] = set()
        
        for directory in directories:
            results = self.scan_directory(directory)
            for result in results:
                if result['path'] not in processed_paths:
                    all_results.append(result)
                    processed_paths.add(result['path'])
        
        return all_results
