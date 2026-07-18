"""
path_repo.py - 下载目录与媒体库路径配置仓储

职责：
- 管理 `config.json` 中的 `paths` 数组。
- 提供下载目录、电影媒体库、剧集媒体库等路径配置的读取、添加和删除能力。
- 供扫描任务决定扫描入口，供归档任务选择目标媒体库根目录。

数据边界：
- 本仓储直接读写配置文件，不操作 SQLite 业务表。
- 路径启用状态、类型和分类由前端设置页维护，后端保存时保持原结构。
- 删除路径时会重排 ID，保证前端列表显示连续。

维护提示：
- 路径字段是文件系统副作用链路入口，注释必须区分 `download` 和 `library`。
- 本仓储不校验路径是否存在；物理可用性由扫描和配置保存链路检查。
"""
import json
import os
from typing import Any, Dict, List

from .base import BaseRepository


class PathRepo(BaseRepository):
    """
    路径配置仓储。

    管理设置页中的下载目录和媒体库目录：
    - `download` 路径用于扫描入口。
    - `library` / `media` / `storage` 路径用于归档目标。
    - `category` 区分 movie / tv。

    本仓储只保存配置，不判断路径是否真实可访问。
    """

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
