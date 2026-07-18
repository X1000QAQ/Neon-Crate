"""
媒体物理过滤器 - 体积和基础样片过滤。

职责：
- 根据最小体积阈值过滤过小文件，降低样片、预告片和残缺文件进入任务表的概率。
- 为 `ScanEngine` 提供单文件物理校验能力。

边界：
- 本模块不做扩展名判断，扩展名白名单由 `ScanEngine` 管理。
- 本模块不解析片名、不访问 TMDB，也不参与 AI 语义识别。
"""
import os
import logging

logger = logging.getLogger(__name__)


class MediaFilter:
    """
    媒体文件物理过滤器。

    当前只执行文件体积检查；目录名和文件名剪枝由 `ScanEngine` 在遍历阶段处理。
    """
    
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
    

