"""
元数据服务包入口。

导出：
- `TMDBAdapter`：TMDB 搜索、详情和外部 ID 查询适配器。

说明：
- NFO 生成、图片下载和校验防火墙由调用方按需直接导入对应模块。
- 保持入口轻量，避免导入包时触发额外网络或文件系统副作用。
"""
from .adapters import TMDBAdapter

__all__ = ["TMDBAdapter"]
