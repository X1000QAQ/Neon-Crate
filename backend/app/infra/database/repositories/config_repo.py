"""
config_repo.py — 配置仓储（v1.0.0）

职责：
  1) 管理磁盘 `config.json`（非敏感字段）与 `secure_keys.json`（6 个敏感密钥的加密存储）
  2) 提供统一配置读写接口（对外保持稳定，调用方零感知）
  3) 承载 v1.0.0 的「创世自愈注入（Genesis Healing）」实现入口（`_inject_ai_defaults`）

核心能力：
  - **敏感键自动加解密**：敏感密钥永不以明文写回 `config.json`
  - **空值兜底**：读取阶段空值用 `DEFAULT_CONFIG` 保底，保证前端首次加载输入框有值
  - **创世自愈注入（Genesis Healing）**：绕过 `get_config()` 的内存兜底层，直接读取磁盘原始配置，
    对 7 个核心字段执行“缺啥补啥”的物理注入，幂等且绝不覆盖用户已填写的非空值

🚨 架构师警告（DO NOT MODIFY）：
  - `get_config/set_config/get_all_config/save_all_config` 属于全局依赖接口，任何语义变更都会造成大面积链路风险。
  - ` _inject_ai_defaults()` 的“绕过兜底、直读直写磁盘”是创世自愈的必要条件，禁止回退到 `get_config()` 判空。
"""
import json
import os
import logging
from typing import Any, Dict

from app.infra.security import get_crypto_manager
from app.infra.database.default_config import DEFAULT_CONFIG

from .base import BaseRepository

logger = logging.getLogger(__name__)

# ── 重置目标映射表（数据驱动，新增分类只需加一行）──────────────────────
RESET_TARGETS_MAP: dict[str, list[str]] = {
    "ai":      ["ai_name", "ai_persona", "expert_archive_rules", "master_router_rules"],
    "regex":   ["filename_clean_regex"],
    "formats": ["supported_video_exts", "supported_subtitle_exts"],
}

# 敏感密钥列表（与 DatabaseManager.SENSITIVE_KEYS 保持一致）
SENSITIVE_KEYS = [
    "tmdb_api_key",
    "os_api_key",
    "sonarr_api_key",
    "radarr_api_key",
    "llm_cloud_key",
    "llm_local_key",
]


class ConfigRepo(BaseRepository):
    """配置仓储：管理 config.json 和 secure_keys.json 的读写及敏感密钥加解密"""

    # ==========================================
    # 配置读写
    # ==========================================

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置（敏感键自动解密，空值自动从 DEFAULT_CONFIG 兜底）"""
        if not os.path.exists(self.config_path):
            # config.json 不存在时直接返回常量兜底
            return DEFAULT_CONFIG.get(key, default)
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[ConfigRepo] config.json 读取失败或损坏，触发容灾降级: {e}")
            return DEFAULT_CONFIG.get(key, default)
        settings = config.get("settings", {})
        if key in SENSITIVE_KEYS:
            if os.path.exists(self.secure_keys_path):
                with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                    secure_data = json.load(f)
                encrypted = secure_data.get(key, "")
                if encrypted:
                    crypto = get_crypto_manager()
                    return crypto.decrypt_api_key(encrypted)
            return default
        value = settings.get(key, None)
        # 空值兜底：从 DEFAULT_CONFIG 取出厂值，保证对外绝不返回空
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_CONFIG.get(key, default)
        return value

    def set_config(self, key: str, value: Any):
        """设置配置（敏感键自动加密）"""
        if not os.path.exists(self.config_path):
            config = {"settings": {}, "paths": []}
        else:
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"[ConfigRepo] config.json 损坏，set_config 重新初始化空配置: {e}")
                config = {"settings": {}, "paths": []}
        if key in SENSITIVE_KEYS:
            secure_data = {}
            if os.path.exists(self.secure_keys_path):
                with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                    secure_data = json.load(f)
            crypto = get_crypto_manager()
            encrypted = crypto.encrypt_api_key(str(value))
            secure_data[key] = encrypted
            with open(self.secure_keys_path, "w", encoding="utf-8") as f:
                json.dump(secure_data, f, indent=4)
            config["settings"][key] = ""
        else:
            config["settings"][key] = value
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)

    def get_all_config(self) -> Dict[str, Any]:
        """获取完整配置（合并解密后的敏感键）"""
        if not os.path.exists(self.config_path):
            return {"settings": {}, "paths": []}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"[ConfigRepo] config.json 读取失败或损坏，get_all_config 触发容灾降级: {e}")
            return {"settings": dict(DEFAULT_CONFIG), "paths": []}
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
            crypto = get_crypto_manager()
            for key in SENSITIVE_KEYS:
                encrypted = secure_data.get(key, "")
                if encrypted:
                    config["settings"][key] = crypto.decrypt_api_key(encrypted)
        # 补全缺失/空值字段：用 DEFAULT_CONFIG 填充，确保前端首次加载时输入框有值
        settings = config.setdefault("settings", {})
        for k, v in DEFAULT_CONFIG.items():
            if k not in settings or settings[k] is None or settings[k] == "":
                settings[k] = v
        return config

    def save_all_config(self, config: Dict[str, Any]):
        """保存完整配置（拦截并加密敏感键）"""
        settings = config.get("settings", {})
        secure_data = {}
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
        crypto = get_crypto_manager()
        for key in SENSITIVE_KEYS:
            value = settings.get(key, "")
            if value and value.strip():
                encrypted = crypto.encrypt_api_key(value)
                secure_data[key] = encrypted
                settings[key] = ""
        with open(self.secure_keys_path, "w", encoding="utf-8") as f:
            json.dump(secure_data, f, indent=4)
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)

    def get_agent_config(self, key: str = None, default: Any = None) -> Any:
        """获取 AI Agent 运行所需的完整配置"""
        config = self.get_all_config().get("settings", {})
        if key:
            return config.get(key, default)
        return {
            "provider":             config.get("llm_provider", "cloud"),
            "cloud_url":            config.get("llm_cloud_url", ""),
            "cloud_key":            config.get("llm_cloud_key", ""),
            "cloud_model":          config.get("llm_cloud_model", ""),
            "local_url":            config.get("llm_local_url", ""),
            "local_key":            config.get("llm_local_key", ""),
            "local_model":          config.get("llm_local_model", ""),
            "ai_persona":           config.get("ai_persona", ""),
            "expert_archive_rules": config.get("expert_archive_rules", ""),
            "master_router_rules":  config.get("master_router_rules", ""),
            "ai_name":              config.get("ai_name", "AI 影音大师"),
        }

    def reset_settings_to_defaults(self, target: str):
        """重置配置为工业级默认值，target 由 RESET_TARGETS_MAP 动态驱动"""
        target = str(target).strip().lower()
        if target not in RESET_TARGETS_MAP:
            valid = ", ".join(RESET_TARGETS_MAP.keys())
            raise ValueError(f"[ERROR] target 必须为 {valid}，收到: {target}")
        defaults = self._load_defaults()
        for key in RESET_TARGETS_MAP[target]:
            self.set_config(key, defaults.get(key, ""))
        logger.info(f"[ConfigRepo] '{target}' 相关配置已重置为工业级默认值: {RESET_TARGETS_MAP[target]}")

    # ==========================================
    # 私有辅助方法
    # ==========================================

    def _load_defaults(self) -> Dict[str, Any]:
        """返回代码固化的出厂默认值（Code as Config，无需读取文件）"""
        return DEFAULT_CONFIG

    def _inject_ai_defaults(self):
        """
        创世自愈注入（Genesis Config Healing）：
        直接读取 config.json 原始内容，检查各关键字段是否缺失或为空，
        缺什么补什么，绝不覆盖用户已填写的非空值。

        ⚠️  不能依赖 get_config() 做存在性判断：
            get_config() 内置了 DEFAULT_CONFIG 兜底，永远不会返回空值，
            导致注入逻辑误判「已有值」而跳过写盘，config.json 里实际是空的。
        正确姿势：直接读取 config.json 的 settings 字典，检查原始值。

        由 DatabaseManager.__init__ 在初始化末尾调用。
        """
        GENESIS_KEYS = [
            "ai_name",
            "ai_persona",
            "expert_archive_rules",
            "master_router_rules",
            "filename_clean_regex",
            "supported_video_exts",
            "supported_subtitle_exts",
        ]

        defaults = self._load_defaults()

        # ── Step 1: 读取 config.json 原始内容（绕过 get_config 兜底层）──
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    raw_config = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"[ConfigRepo] config.json 读取失败，创世注入使用空配置兜底: {e}")
                raw_config = {"settings": {}, "paths": []}
        else:
            # config.json 不存在 → 全量注入
            raw_config = {"settings": {}, "paths": []}

        raw_settings = raw_config.get("settings", {})

        # ── Step 2: 缺啥补啥（直接比对原始 settings，而非经过兜底的 get_config）──
        injected_fields = []
        for key in GENESIS_KEYS:
            raw_val = raw_settings.get(key, None)
            # 缺失（None）或空字符串 → 注入默认值
            if raw_val is None or (isinstance(raw_val, str) and not raw_val.strip()):
                if key in defaults:
                    self.set_config(key, defaults[key])
                    injected_fields.append(key)

        if injected_fields:
            logger.info(
                f"[ConfigRepo] 创世自愈注入完成，补全 {len(injected_fields)} 个字段: "
                f"{injected_fields}"
            )
        else:
            logger.debug("[ConfigRepo] 创世自愈检查完毕，所有关键字段均已存在，无需注入。")
