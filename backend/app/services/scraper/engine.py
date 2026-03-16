"""
并发扫描引擎 - 多线程文件扫描

核心特性：
1. 并发扫描：ThreadPoolExecutor 多线程
2. 递归遍历：支持深度目录扫描
3. 视频过滤：仅扫描视频文件
4. 去重机制：基于文件路径去重
"""
import os
import re
import asyncio
from pathlib import Path
from typing import List, Dict, Set, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

from .filters import MediaFilter
from .cleaner import MediaCleaner
from app.infra.constants import VIDEO_EXTS_EXTENDED

logger = logging.getLogger(__name__)


def _parse_ext_config(raw: str) -> frozenset:
    """将逗号分隔的后缀字符串解析为小写 frozenset，去除多余空格。"""
    parts = [e.strip().lower() for e in raw.split(",") if e.strip()]
    # 确保每个后缀以 '.' 开头
    parts = [e if e.startswith(".") else f".{e}" for e in parts]
    return frozenset(parts)


class ScanEngine:
    """并发扫描引擎"""

    # 静态兜底（db 读取失败时使用）
    _VIDEO_EXTS_FALLBACK = VIDEO_EXTS_EXTENDED

    def __init__(self, max_workers: int = 4, min_size_mb: int = 50, db_manager=None, known_paths: set = None, known_inodes: set = None):
        """
        初始化扫描引擎
        
        Args:
            max_workers: 最大并发线程数
            min_size_mb: 最小文件体积限制（MB）
            db_manager: 数据库管理器（用于加载自定义正则）
            known_paths: 已入库文件路径集合（用于前置过滤）
            known_inodes: 已入库文件物理指纹集合（用于硬链接防重）
        """
        self.max_workers = max_workers
        self.min_size_mb = min_size_mb
        self.filter = MediaFilter(min_size_mb=min_size_mb)
        self.cleaner = MediaCleaner(db_manager=db_manager)
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
            视频文件列表，每个元素包含 path, file_name, size, clean_name, year, is_tv, season, episode
        """
        if not os.path.exists(directory):
            logger.warning(f"目录不存在: {directory}")
            return []
        
        logger.info(f"开始扫描目录: {directory} (递归={recursive})")
        
        # 收集所有视频文件
        video_files = self._collect_video_files(directory, recursive)
        logger.info(f"发现 {len(video_files)} 个视频文件")
        
        # 并发过滤和清洗
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
        """并发处理文件（过滤 + 清洗）"""
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
        处理单个文件：过滤 + MediaCleaner 清洗
        
        Returns:
            符合条件的文件信息，或 None（不符合条件）
        """
        try:
            # 1. 物理过滤（体积检查）
            if not self.filter.check_file_size(file_path):
                return None
            
            # 2. 获取文件信息
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # 3. 使用 MediaCleaner 进行强大的清洗和提取
            extract_result = self.cleaner.clean_and_extract(file_name)

            # 3.1 若文件名未能提取到季号，尝试从父级目录名补充
            #     匹配：Season 1 / Season 01 / S01 / S1
            if extract_result.get('season') is None:
                _season_from_path = None
                for part in Path(file_path).parts:
                    m = re.search(r'(?:Season|S)\s*(\d{1,2})\b', part, re.IGNORECASE)
                    if m:
                        _season_from_path = int(m.group(1))
                if _season_from_path is not None:
                    extract_result['season'] = _season_from_path
                    # 只要有季号就视为剧集
                    extract_result['is_tv'] = True
                    logger.debug(f'[SCAN] 从路径补充季号: {file_path} -> season={_season_from_path}')
            
            # 4. 过滤广告文件
            if extract_result.get('is_ad', False):
                logger.debug(f"过滤广告文件: {file_name}")
                return None
            
            return {
                'path': file_path,
                'file_name': file_name,
                'size': file_size,
                'clean_name': extract_result['clean_name'],
                'year': extract_result['year'],
                'is_tv': extract_result['is_tv'],
                'season': extract_result['season'],
                'episode': extract_result['episode']
            }
        
        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {e}")
            return None
    
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
