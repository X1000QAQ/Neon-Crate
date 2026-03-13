"""
物理过滤器 - 50MB 体积过滤

核心特性：
1. 体积过滤：默认 50MB 最小体积
2. 路径过滤：排除特定目录（sample、extras 等）
3. 扩展名过滤：仅保留视频文件
"""
import os
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
    

