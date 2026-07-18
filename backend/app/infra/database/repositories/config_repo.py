"""
config_repo.py - 配置仓储、敏感密钥分离与提示词文件化

职责：
- 管理 `config.json` 中的非敏感系统配置、路径配置和提示词引用。
- 管理 `secure_keys.json` 中的敏感密钥密文，读取时自动解密，保存时自动加密。
- 将长文本提示词字段写入 `data/prompts/*.txt`，在 `config.json` 中只保留 `@prompts/` 引用。
- 启动时执行创世自愈注入，补齐关键默认配置，避免冷启动空配置导致前端或 AI 链路失效。

废弃功能边界：
- 旧版 `filename_clean_regex` 已废弃，仅作为历史配置清理名单存在。
- 当前系统不再支持用户配置“物理正则清洗”。文件名语义清洗由 AI Agent 和提示词完成。
- `DEPRECATED_CONFIG_KEYS` 只负责读写时忽略、启动时剥离旧字段，不代表该功能仍然可用。

维护提示：
- `get_config()`、`set_config()`、`get_all_config()`、`save_all_config()` 是全局依赖接口，禁止改变返回结构。
- `_inject_ai_defaults()` 必须直读磁盘原始配置，不能回退为通过 `get_config()` 判空。
"""
import json
import os
import logging
from typing import Any, Dict

from app.infra.security import get_crypto_manager
from app.infra.database.default_config import DEFAULT_CONFIG

from .base import BaseRepository

logger = logging.getLogger(__name__)

# 废弃字段清理名单：用于剥离历史 config.json 中残留的旧版文件名正则配置。
# 当前系统不再支持用户配置“物理正则清洗”，语义识别由 AI Agent 完成。
# 保留此名单是为了幂等清理旧配置，不代表该功能仍然可用。
DEPRECATED_CONFIG_KEYS = frozenset({"filename_clean_regex"})

# 提示词字段 → 对应的 prompts/ 文件名（写入时自动路由到文件，config.json 只存引用）
PROMPT_FILE_KEYS: dict[str, str] = {
    "ai_persona":           "ai_persona.txt",
    "expert_archive_rules": "expert_archive_rules.txt",
    "master_router_rules":  "master_router_rules.txt",
}

# ── 重置目标映射表（数据驱动，新增分类只需加一行）──────────────────────
RESET_TARGETS_MAP: dict[str, list[str]] = {
    "ai":      ["ai_name", "ai_persona", "expert_archive_rules", "master_router_rules"],
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
    """
    配置仓储。

    负责三类配置介质的读写协调：
    - `config.json`：非敏感设置和路径数组。
    - `secure_keys.json`：敏感 API Key 密文。
    - `data/prompts/*.txt`：AI 长提示词正文。

    重要边界：废弃配置只允许被清理，不允许重新参与业务逻辑。
    """

    # ==========================================
    # 配置读写
    # ==========================================

    def _load_prompt_file(self, ref: str) -> str:
        """加载 @prompts/ 引用的文本文件内容"""
        if not ref.startswith("@prompts/"):
            return ref
        rel_path = ref[9:]  # 去掉 '@prompts/' 前缀
        prompts_dir = os.path.join(os.path.dirname(self.config_path), "prompts")
        file_path = os.path.join(prompts_dir, rel_path)
        if not os.path.exists(file_path):
            logger.warning(f"[ConfigRepo] 提示词文件不存在: {file_path}，返回空字符串")
            return ""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError as e:
            logger.error(f"[ConfigRepo] 提示词文件读取失败: {file_path}, {e}")
            return ""

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        读取单个配置项。

        读取顺序：
        1. 废弃字段直接返回 default，避免历史正则配置继续生效。
        2. 敏感键从 `secure_keys.json` 解密读取。
        3. 普通键从 `config.json.settings` 读取。
        4. 空值或缺失值回退到 `DEFAULT_CONFIG`。
        5. `@prompts/` 引用会被展开为实际提示词文件内容。
        """
        if key in DEPRECATED_CONFIG_KEYS:
            return default
        if not os.path.exists(self.config_path):
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
        if value is None or (isinstance(value, str) and not value.strip()):
            return DEFAULT_CONFIG.get(key, default)
        if isinstance(value, str) and value.startswith("@prompts/"):
            return self._load_prompt_file(value)
        return value

    def set_config(self, key: str, value: Any):
        """
        写入单个配置项。

        写入策略：
        - 废弃字段直接忽略，防止旧版 `filename_clean_regex` 被重新写回。
        - 提示词字段写入 `data/prompts/*.txt`，`config.json` 只保存引用。
        - 敏感键加密写入 `secure_keys.json`，`config.json.settings` 中保留空字符串占位。
        - 普通键直接写入 `config.json.settings`。
        """
        if key in DEPRECATED_CONFIG_KEYS:
            logger.info(f"[ConfigRepo] 已忽略废弃配置字段 {key}")
            return
        
        # 提示词字段：写入 txt 文件，config.json 保留引用
        if key in PROMPT_FILE_KEYS:
            prompts_dir = os.path.join(os.path.dirname(self.config_path), "prompts")
            os.makedirs(prompts_dir, exist_ok=True)
            file_path = os.path.join(prompts_dir, PROMPT_FILE_KEYS[key])
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(str(value))
                logger.debug(f"[ConfigRepo] 提示词已写入文件: {file_path}")
            except OSError as e:
                logger.error(f"[ConfigRepo] 提示词文件写入失败: {file_path}, {e}")
            # config.json 中保留引用
            if not os.path.exists(self.config_path):
                config = {"settings": {}, "paths": []}
            else:
                try:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        config = json.load(f)
                except (json.JSONDecodeError, OSError):
                    config = {"settings": {}, "paths": []}
            config["settings"][key] = f"@prompts/{PROMPT_FILE_KEYS[key]}"
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
            return
        
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
        """
        读取完整配置，供 `/settings` 接口和设置页使用。

        返回内容：
        - `settings`：合并默认值、解密后的敏感键和展开后的提示词文本。
        - `paths`：下载目录和媒体库路径配置。

        注意：
        - 废弃字段会在返回前从 settings 中剥离。
        - 前端需要真实密钥值用于编辑态回显，因此这里会返回解密后的敏感键。
        - 展示层是否遮罩由前端负责，仓储层只维护数据契约。
        """
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
        settings = config.setdefault("settings", {})
        for deprecated in DEPRECATED_CONFIG_KEYS:
            settings.pop(deprecated, None)
        for k, v in DEFAULT_CONFIG.items():
            if k not in settings or settings[k] is None or settings[k] == "":
                settings[k] = v
        # 展开 @prompts/ 引用为实际文件内容（供前端显示和 AI 使用）
        for k, v in settings.items():
            if isinstance(v, str) and v.startswith("@prompts/"):
                settings[k] = self._load_prompt_file(v)
        return config

    def save_all_config(self, config: Dict[str, Any]):
        """
        保存完整配置，供设置页“保存”操作使用。

        写入流程：
        1. 先剥离废弃字段，避免历史 `filename_clean_regex` 重新污染配置。
        2. 将 AI 提示词长文本写入 prompts 文件，并在 `config.json` 中保存引用。
        3. 将敏感键加密写入 `secure_keys.json`，并清空 `config.json` 中的明文。
        4. 使用临时文件 + `os.replace()` 原子写入 `config.json`。
        """
        settings = config.get("settings", {})
        for deprecated in DEPRECATED_CONFIG_KEYS:
            settings.pop(deprecated, None)
        
        # 先处理提示词字段：写入 txt 文件，config.json 中保留引用
        prompts_dir = os.path.join(os.path.dirname(self.config_path), "prompts")
        os.makedirs(prompts_dir, exist_ok=True)
        for key, filename in PROMPT_FILE_KEYS.items():
            value = settings.get(key, "")
            if value and not value.startswith("@prompts/"):
                # 前端传来的是完整内容，写入文件
                file_path = os.path.join(prompts_dir, filename)
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(str(value))
                    logger.debug(f"[ConfigRepo] 提示词已写入文件: {file_path}")
                except OSError as e:
                    logger.error(f"[ConfigRepo] 提示词文件写入失败: {file_path}, {e}")
                # config.json 中保留引用
                settings[key] = f"@prompts/{filename}"
            elif not value or value.startswith("@prompts/"):
                # 如果值为空或已经是引用，保持不变
                settings[key] = value if value else f"@prompts/{filename}"
        
        # 处理敏感键加密
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
        
        # 写入 config.json
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
        创世自愈注入（Genesis Config Healing）。

        目标：
        - 在冷启动或旧配置升级时补齐 AI 名称、提示词规则和格式扩展名。
        - 只补缺失或空值字段，不覆盖用户已经填写的非空配置。
        - 同步剥离历史废弃字段，防止旧版文件名正则配置继续污染当前链路。

        为什么必须直读磁盘：
        `get_config()` 内置 `DEFAULT_CONFIG` 兜底，无法判断磁盘原始配置是否真的缺失。
        因此这里必须绕过 `get_config()`，直接读取 `config.json.settings` 原始值。

        物理正则边界：
        `filename_clean_regex` 只在这里被幂等剥离；系统不会恢复或执行用户自定义正则清洗。
        """
        GENESIS_KEYS = [
            "ai_name",
            "ai_persona",
            "expert_archive_rules",
            "master_router_rules",
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

        # ── Step 1.5: 剥离 Phase 5A 废弃字段（幂等自愈）────────────────
        purged = [k for k in DEPRECATED_CONFIG_KEYS if raw_settings.pop(k, None) is not None]
        if purged:
            tmp_path = self.config_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(raw_config, f, indent=4, ensure_ascii=False)
            os.replace(tmp_path, self.config_path)
            logger.info(f"[ConfigRepo] 创世自愈剥离废弃字段: {purged}")

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
