"""
path_repo.py - 路径管理仓储

职责：管理 config.json 中的 paths 数组，
     处理下载目录和媒体库路径的增删改查。

迁入方法（原 db_manager.py）：
  - get_managed_paths  (原行 397)
  - add_managed_path   (原行 405)
  - delete_managed_path (原行 421)

依赖：文件系统（config.json），无数据库连接依赖。

Impact 分析（2026-03-12）：
  get_managed_paths    → HIGH（被 get_active_library_path 调用 → 刮削流程）
  add_managed_path     → LOW（图谱无直接调用者）
  delete_managed_path  → LOW（图谱无直接调用者）
  迁移安全：外观层接口不变，所有调用方零感知。
"""
import json
import os
from typing import Any, Dict, List

from .base import BaseRepository


class PathRepo(BaseRepository):
    """路径管理仓储：管理 config.json 中的 paths 数组"""

    def get_managed_paths(self) -> List[Dict[str, Any]]:
        """获取所有路径配置"""
        if not os.path.exists(self.config_path):
            return []
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        return config.get("paths", [])

    def add_managed_path(self, p_type: str, path: str, category: str):
        """添加路径配置"""
        if not os.path.exists(self.config_path):
            config = {"settings": {}, "paths": []}
        else:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        paths = config.get("paths", [])
        new_id = max([p.get("id", 0) for p in paths], default=0) + 1
        paths.append({"id": new_id, "type": p_type, "path": path, "category": category, "enabled": True})
        config["paths"] = paths
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)

    def delete_managed_path(self, path_id: int):
        """删除路径配置（同时重排 ID 保持连续）"""
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        paths = [p for p in config.get("paths", []) if p.get("id") != path_id]
        # 重排 ID 保持连续
        for i, p in enumerate(paths, 1):
            p["id"] = i
        config["paths"] = paths
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)
