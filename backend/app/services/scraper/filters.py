"""
物理过滤器 - 50MB 体积过滤

核心特性：
1. 体积过滤：默认 50MB 最小体积
2. 路径过滤：排除特定目录（sample、extras 等）
3. 扩展名过滤：仅保留视频文件
"""
import os
from pathlib import Path
from typing import Set
import logging

logger = logging.getLogger(__name__)


class MediaFilter:
    """媒体文件过滤器"""
    
    # 默认最小体积（50MB）
    DEFAULT_MIN_SIZE = 50 * 1024 * 1024
    
    # 排除的目录名（小写）
    EXCLUDED_DIRS = {
        'sample', 'samples', 'extras', 'featurettes', 
        'behind the scenes', 'deleted scenes', 'trailers'
    }
    
    # 排除的文件名关键词（小写）
    EXCLUDED_KEYWORDS = {
        'sample', 'trailer', 'preview', 'teaser'
    }
    
    def __init__(self, min_size_mb: int = 50):
        """
        初始化过滤器
        
        Args:
            min_size_mb: 最小体积（MB）
        """
        self.min_size = min_size_mb * 1024 * 1024
        logger.info(f"过滤器初始化: 最小体积 {min_size_mb}MB")
    
    def check_file_size(self, file_path: str) -> bool:
        """
        检查文件体积是否符合要求
        
        Args:
            file_path: 文件路径
        
        Returns:
            True 表示符合要求，False 表示过小
        """
        try:
            size = os.path.getsize(file_path)
            if size < self.min_size:
                logger.debug(f"文件过小: {file_path} ({size / 1024 / 1024:.2f}MB)")
                return False
            return True
        except Exception as e:
            logger.error(f"检查文件大小失败 {file_path}: {e}")
            return False
    
    def check_path(self, file_path: str) -> bool:
        """
        检查路径是否在排除列表中
        
        Args:
            file_path: 文件路径
        
        Returns:
            True 表示可以处理，False 表示应排除
        """
        path_lower = file_path.lower()
        
        # 检查目录名
        for excluded_dir in self.EXCLUDED_DIRS:
            if f"/{excluded_dir}/" in path_lower or f"\\{excluded_dir}\\" in path_lower:
                logger.debug(f"路径被排除: {file_path} (目录: {excluded_dir})")
                return False
        
        # 检查文件名关键词
        filename = os.path.basename(file_path).lower()
        for keyword in self.EXCLUDED_KEYWORDS:
            if keyword in filename:
                logger.debug(f"文件名被排除: {file_path} (关键词: {keyword})")
                return False
        
        return True
    
    def filter_files(self, file_paths: list) -> list:
        """
        批量过滤文件
        
        Args:
            file_paths: 文件路径列表
        
        Returns:
            符合条件的文件路径列表
        """
        filtered = []
        
        for file_path in file_paths:
            if self.check_path(file_path) and self.check_file_size(file_path):
                filtered.append(file_path)
        
        logger.info(f"过滤完成: {len(file_paths)} -> {len(filtered)}")
        return filtered
    
    def get_file_info(self, file_path: str) -> dict:
        """
        获取文件详细信息
        
        Args:
            file_path: 文件路径
        
        Returns:
            包含 size, size_mb, extension 的字典
        """
        try:
            size = os.path.getsize(file_path)
            ext = Path(file_path).suffix.lower()
            
            return {
                'size': size,
                'size_mb': round(size / 1024 / 1024, 2),
                'extension': ext,
                'passes_filter': size >= self.min_size
            }
        except Exception as e:
            logger.error(f"获取文件信息失败 {file_path}: {e}")
            return {
                'size': 0,
                'size_mb': 0,
                'extension': '',
                'passes_filter': False
            }
