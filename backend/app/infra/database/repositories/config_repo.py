"""
config_repo.py - 配置仓储

职责：管理 config.json 和 secure_keys.json 的读写，
     处理 6 个敏感密钥的自动加解密。

迁入方法（原 db_manager.py）：
  - get_config              (原行 313)
  - set_config              (原行 331)
  - get_all_config          (原行 356)
  - save_all_config         (原行 372)
  - get_agent_config        (原行 685)
  - reset_settings_to_defaults (原行 1008)
  - _load_defaults          (原行 280) [私有辅助]
  - _inject_ai_defaults     (原行 292) [私有辅助，由 DatabaseManager.__init__ 调用]

Impact 分析（2026-03-12）：
  get_config    → CRITICAL（18 impacted，12 direct，20 processes）
  set_config    → CRITICAL（12 impacted，6 direct，16 processes）
  get_all_config → CRITICAL（13 impacted，4 direct，15 processes）
  迁移安全：外观层接口不变，所有调用方（agent.py、scrape_task、scan_task 等）零感知。

依赖：get_crypto_manager()（来自 app.infra.security）
"""
import json
import os
import logging
from typing import Any, Dict

from app.infra.security import get_crypto_manager
from app.infra.database.default_config import DEFAULT_CONFIG

from .base import BaseRepository

logger = logging.getLogger(__name__)

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
        """重置配置为工业级默认值，target: 'ai' 或 'regex'"""
        target = str(target).strip().lower()
        defaults = self._load_defaults()

        if target == "ai":
            self.set_config("ai_name", defaults.get("ai_name", "AI 智能助理"))
            self.set_config("ai_persona", defaults.get("ai_persona", ""))
            self.set_config("expert_archive_rules", defaults.get("expert_archive_rules", ""))
            self.set_config("master_router_rules", defaults.get("master_router_rules", ""))
            logger.info("[ConfigRepo] AI 规则已重置为工业级默认值")
        elif target == "regex":
            self.set_config("filename_clean_regex", defaults.get("filename_clean_regex", ""))
            logger.info("[ConfigRepo] 正则清洗规则已重置为工业级默认值（15条规则）")
        else:
            raise ValueError(f"[ERROR] target 必须为 'ai' 或 'regex'，收到: {target}")

    # ==========================================
    # 私有辅助方法
    # ==========================================

    def _load_defaults(self) -> Dict[str, Any]:
        """返回代码固化的出厂默认值（Code as Config，无需读取文件）"""
        return DEFAULT_CONFIG

    def _inject_ai_defaults(self):
        """
        灵魂注入：将 AI 规则注入为系统默认值。
        仅在字段为空时注入，避免覆盖用户自定义配置。
        由 DatabaseManager.__init__ 在初始化末尾调用。
        """
        from app.services.scraper.cleaner import MediaCleaner  # noqa: F401

        defaults = self._load_defaults()
        injected_fields = []

        for key in ["ai_name", "ai_persona", "expert_archive_rules", "master_router_rules", "filename_clean_regex"]:
            if key in defaults and not self.get_config(key, "").strip():
                self.set_config(key, defaults[key])
                injected_fields.append(key)

        if injected_fields:
            logger.info(f"[ConfigRepo] 已注入 {len(injected_fields)} 个 AI 规则默认值")
