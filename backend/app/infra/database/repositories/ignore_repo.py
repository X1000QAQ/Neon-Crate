"""
ignore_repo.py - 持久化忽略清单管理器

职责：
- 读写 data/ignore_paths.txt，每行一个规范化路径。
- 提供 add / remove / contains / list 四个展面方法。
- 文件不存在时自动创建；写入时原子替换（tmp → rename），防止写入半途崩溃。

设计原则：
- 与数据库完全解耦，数据库重置不影响此文件。
- 路径规范化使用 os.path.normcase(os.path.normpath(...))，跨平台一致。
- 线程安全：用 threading.Lock 保护读写，与 DatabaseManager 共享同一进程。
"""
import os
import threading
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_IGNORE_FILE_NAME = "ignore_paths.txt"


class IgnoreRepo:
    """
    持久化忽略清单仓储。

    文件格式：UTF-8 纯文本，每行一个规范化绝对路径，# 开头为注释行。
    典型路径：data/ignore_paths.txt（与 config.json 同级）。
    """

    def __init__(self, data_dir: str = "data"):
        self._path = os.path.join(data_dir, _IGNORE_FILE_NAME)
        self._lock = threading.Lock()
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self._path):
            Path(self._path).write_text(
                "# Neon-Crate 持久化忽略清单\n"
                "# 每行一个绝对路径，扫描时将永久跳过这些文件。\n"
                "# 此文件独立于数据库，数据库重置后仍然生效。\n",
                encoding="utf-8",
            )

    # ── 内部工具 ──────────────────────────────────────────────────────

    @staticmethod
    def _normalize(path: str) -> str:
        return os.path.normcase(os.path.normpath(path))

    def _read_entries(self) -> tuple[set, list]:
        """返回 (规范化路径集合, 原始行列表（含注释））"""
        if not os.path.exists(self._path):
            return set(), []
        lines = Path(self._path).read_text(encoding="utf-8").splitlines()
        norm_set: set = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                norm_set.add(self._normalize(stripped))
        return norm_set, lines

    def _write_lines(self, lines: list):
        """原子写入：先写 .tmp，再 replace。"""
        tmp = self._path + ".tmp"
        Path(tmp).write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(tmp, self._path)

    # ── 公开接口 ──────────────────────────────────────────────────────

    def contains(self, path: str) -> bool:
        """判断路径是否在忽略清单中（O(1)）。"""
        with self._lock:
            norm_set, _ = self._read_entries()
            return self._normalize(path) in norm_set

    def add(self, path: str) -> bool:
        """
        将路径加入忽略清单。

        Returns:
            True  — 新增成功
            False — 路径已存在，无需重复写入
        """
        with self._lock:
            norm_set, lines = self._read_entries()
            norm = self._normalize(path)
            if norm in norm_set:
                return False
            lines.append(path)
            self._write_lines(lines)
            logger.info(f"[IGNORE] 已加入忽略清单: {path}")
            return True

    def add_batch(self, paths: List[str]) -> int:
        """批量加入忽略清单，返回实际新增数量。"""
        with self._lock:
            norm_set, lines = self._read_entries()
            added = 0
            for path in paths:
                norm = self._normalize(path)
                if norm not in norm_set:
                    lines.append(path)
                    norm_set.add(norm)
                    added += 1
            if added:
                self._write_lines(lines)
                logger.info(f"[IGNORE] 批量加入忽略清单: {added} 条")
            return added

    def remove(self, path: str) -> bool:
        """
        从忽略清单移除路径（取消忽略）。

        Returns:
            True  — 移除成功
            False — 路径不存在于清单
        """
        with self._lock:
            norm_set, lines = self._read_entries()
            norm = self._normalize(path)
            if norm not in norm_set:
                return False
            new_lines = [
                l for l in lines
                if l.strip().startswith("#") or self._normalize(l.strip()) != norm
            ]
            self._write_lines(new_lines)
            logger.info(f"[IGNORE] 已移出忽略清单: {path}")
            return True

    def list_all(self) -> List[str]:
        """返回所有被忽略的路径列表（不含注释行）。"""
        with self._lock:
            _, lines = self._read_entries()
            return [
                l.strip() for l in lines
                if l.strip() and not l.strip().startswith("#")
            ]

    def load_set(self) -> frozenset:
        """返回规范化路径的 frozenset，供扫描时 O(1) 查找。"""
        with self._lock:
            norm_set, _ = self._read_entries()
            return frozenset(norm_set)
