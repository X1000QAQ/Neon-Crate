#!/usr/bin/env python3
"""Migrate runtime config to the Phase 5A semantic configuration contract."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
DEFAULT_CONFIG_PATH = BACKEND_ROOT / "app" / "infra" / "database" / "default_config.py"
CONFIG_PATH = BACKEND_ROOT / "data" / "config.json"


def _load_default_config() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("phase5a_default_config", DEFAULT_CONFIG_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load default config from {DEFAULT_CONFIG_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    default_config = getattr(module, "DEFAULT_CONFIG", None)
    if not isinstance(default_config, dict):
        raise RuntimeError("DEFAULT_CONFIG must be a dict")
    return default_config


DEFAULT_CONFIG = _load_default_config()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"settings": {}, "paths": []}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"config root must be an object: {path}")
    data.setdefault("settings", {})
    data.setdefault("paths", [])
    if not isinstance(data["settings"], dict):
        raise ValueError("config.settings must be an object")
    if not isinstance(data["paths"], list):
        raise ValueError("config.paths must be a list")
    return data


def migrate_config(config_path: Path = CONFIG_PATH, *, backup: bool = True) -> dict[str, Any]:
    expert_rules = DEFAULT_CONFIG.get("expert_archive_rules")
    if not isinstance(expert_rules, str) or "10 个键" not in expert_rules:
        raise RuntimeError("DEFAULT_CONFIG['expert_archive_rules'] is not the Phase 5A 10-field schema")

    config = _load_json(config_path)
    settings = config.setdefault("settings", {})

    removed_regex = settings.pop("filename_clean_regex", None) is not None
    settings["expert_archive_rules"] = expert_rules

    config_path.parent.mkdir(parents=True, exist_ok=True)
    if backup and config_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = config_path.with_suffix(config_path.suffix + f".bak.phase5a-{stamp}")
        shutil.copy2(config_path, backup_path)
    else:
        backup_path = None

    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    os.replace(tmp_path, config_path)

    return {
        "config_path": str(config_path),
        "backup_path": str(backup_path) if backup_path else None,
        "removed_filename_clean_regex": removed_regex,
        "expert_archive_rules_schema": "10-field",
        "settings_keys": sorted(settings.keys()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Neon Crate config.json to Phase 5A.")
    parser.add_argument(
        "--config",
        type=Path,
        default=CONFIG_PATH,
        help="Path to config.json. Defaults to backend/data/config.json.",
    )
    parser.add_argument("--no-backup", action="store_true", help="Do not create a backup copy.")
    args = parser.parse_args()

    result = migrate_config(args.config.resolve(), backup=not args.no_backup)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
