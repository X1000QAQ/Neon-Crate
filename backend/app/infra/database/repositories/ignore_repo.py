"""Persistent, scoped manual-ignore rules.

The ignore-rule file is intentionally independent from SQLite so a database reset
never re-enqueues files the user deliberately excluded.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

logger = logging.getLogger(__name__)

RuleScope = Literal["file", "directory"]
_RULE_FILE_NAME = "ignore_rules.json"
_RULE_FILE_VERSION = 1


class IgnoreRepo:
    """Owns canonicalization, matching, folding, and atomic persistence of ignore rules."""

    def __init__(self, data_dir: str = "data"):
        self._path = os.path.join(data_dir, _RULE_FILE_NAME)
        self._lock = threading.RLock()
        os.makedirs(data_dir, exist_ok=True)
        if not os.path.exists(self._path):
            self._write_rules([])

    @staticmethod
    def normalize_path(path: str) -> str:
        if not isinstance(path, str) or not path.strip() or "\x00" in path:
            raise ValueError("路径不能为空且不得包含 NUL 字符")
        if not os.path.isabs(path):
            raise ValueError("忽略规则路径必须是绝对路径")
        normalized = os.path.normcase(os.path.normpath(path.strip()))
        if normalized != os.path.sep:
            normalized = normalized.rstrip("/\\")
        return normalized

    @classmethod
    def _is_same_or_descendant(cls, path: str, directory: str) -> bool:
        try:
            return os.path.commonpath([path, directory]) == directory
        except ValueError:
            return False

    @classmethod
    def _matches(cls, rule: dict[str, Any], candidate_path: str) -> bool:
        if rule["scope"] == "file":
            return candidate_path == rule["path"]
        return cls._is_same_or_descendant(candidate_path, rule["path"])

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def _read_rules(self) -> list[dict[str, Any]]:
        try:
            with open(self._path, encoding="utf-8") as rule_file:
                payload = json.load(rule_file)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"忽略规则文件不可读取: {exc}") from exc

        if payload.get("version") != _RULE_FILE_VERSION or not isinstance(payload.get("rules"), list):
            raise RuntimeError("忽略规则文件格式无效")

        rules: list[dict[str, Any]] = []
        for item in payload["rules"]:
            if not isinstance(item, dict) or item.get("scope") not in {"file", "directory"}:
                raise RuntimeError("忽略规则文件包含无效规则")
            rules.append({
                "id": str(item["id"]),
                "scope": item["scope"],
                "path": self.normalize_path(item["path"]),
                "created_at": str(item["created_at"]),
            })
        return rules

    def _write_rules(self, rules: Iterable[dict[str, Any]]) -> None:
        payload = {"version": _RULE_FILE_VERSION, "rules": list(rules)}
        tmp_path = f"{self._path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as rule_file:
            json.dump(payload, rule_file, ensure_ascii=False, indent=2)
            rule_file.write("\n")
        os.replace(tmp_path, self._path)

    def _derive_rule_path(self, scope: RuleScope, paths: Iterable[str]) -> str:
        canonical_paths = list(dict.fromkeys(self.normalize_path(path) for path in paths))
        if not canonical_paths:
            raise ValueError("至少提供一个文件路径")
        if scope == "file":
            if len(canonical_paths) != 1:
                raise ValueError("文件规则必须且只能指定一个文件路径")
            return canonical_paths[0]
        if scope != "directory":
            raise ValueError("规则作用域必须是 file 或 directory")
        directories = [os.path.dirname(path) for path in canonical_paths]
        try:
            return self.normalize_path(os.path.commonpath(directories))
        except ValueError as exc:
            raise ValueError("目录规则不能跨越不同文件系统根目录") from exc

    def create_rule(self, scope: RuleScope, paths: Iterable[str]) -> dict[str, Any]:
        """Create the minimal rule covering paths, or return its existing cover rule."""
        with self._lock:
            rule_path = self._derive_rule_path(scope, paths)
            rules = self._read_rules()

            for rule in rules:
                if self._matches(rule, rule_path):
                    return {"created": False, "rule": rule, "removed_rule_ids": []}

            removed_rule_ids: list[str] = []
            if scope == "directory":
                remaining_rules: list[dict[str, Any]] = []
                for rule in rules:
                    if self._is_same_or_descendant(rule["path"], rule_path):
                        removed_rule_ids.append(rule["id"])
                    else:
                        remaining_rules.append(rule)
                rules = remaining_rules

            rule = {
                "id": str(uuid.uuid4()),
                "scope": scope,
                "path": rule_path,
                "created_at": self._utc_now(),
            }
            rules.append(rule)
            self._write_rules(rules)
            logger.info("[IGNORE] 创建 %s 规则: %s", scope, rule_path)
            return {"created": True, "rule": rule, "removed_rule_ids": removed_rule_ids}

    def list_rules(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self._read_rules(), key=lambda rule: (rule["path"], rule["scope"]))

    def delete_rule(self, rule_id: str) -> bool:
        with self._lock:
            rules = self._read_rules()
            remaining_rules = [rule for rule in rules if rule["id"] != rule_id]
            if len(remaining_rules) == len(rules):
                return False
            self._write_rules(remaining_rules)
            logger.info("[IGNORE] 删除规则: %s", rule_id)
            return True

    def clear_rules(self) -> int:
        with self._lock:
            rules = self._read_rules()
            self._write_rules([])
            logger.info("[IGNORE] 清空 %s 条规则", len(rules))
            return len(rules)

    def match(self, path: str) -> Optional[dict[str, Any]]:
        candidate_path = self.normalize_path(path)
        with self._lock:
            rules = self._read_rules()
        matching_rules = [rule for rule in rules if self._matches(rule, candidate_path)]
        if not matching_rules:
            return None
        return min(matching_rules, key=lambda rule: (len(rule["path"]), rule["scope"] == "file"))

    def filter_matched(self, paths: Iterable[str]) -> dict[str, dict[str, Any]]:
        matches: dict[str, dict[str, Any]] = {}
        for path in paths:
            rule = self.match(path)
            if rule:
                matches[path] = rule
        return matches
