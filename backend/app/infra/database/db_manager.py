"""
数据库管理器 - SQLite WAL 模式 + 原子写入 + 敏感密钥加密存储

核心特性：
1. WAL 模式：提升并发性能
2. 原子写入：配置文件采用 .tmp 替换机制
3. 线程级连接池：使用 threading.local() 实现连接复用，彻底消除高频 connect/close 开销
4. 敏感密钥加密：自动拦截并加密 6 个敏感键
5. 自动明文密钥迁移：首次启动时检测并迁移明文密钥
"""
import os
import json
import sqlite3
import threading
from typing import Any, Optional, Dict, List
from pathlib import Path

from app.infra.security import get_crypto_manager


class DatabaseManager:
    """数据库管理器"""

    SENSITIVE_KEYS = [
        "tmdb_api_key",
        "os_api_key",
        "sonarr_api_key",
        "radarr_api_key",
        "llm_cloud_key",
        "llm_local_key"
    ]

    def __init__(self, db_path: str = "data/media_database.db", config_path: str = "data/config.json"):
        self.db_path = db_path
        self.config_path = config_path
        self.secure_keys_path = "data/secure_keys.json"
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_lock = threading.Lock()
        self._local = threading.local()
        # 注册迁移清单（幂等，多次调用无副作用）
        self.__class__._register_migrations()
        self._init_database()
        self._migrate_database()
        self._migrate_sensitive_keys()
        self._inject_ai_defaults()

    def _get_conn(self) -> sqlite3.Connection:
        """
        获取当前线程的持久化 SQLite 连接（线程级连接池核心方法）

        - 若当前线程已有连接，直接复用，零开销
        - 否则创建新连接，设置 WAL 模式 + row_factory 并缓存到线程本地存储
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    # ==========================================
    # 版本化迁移引擎
    # ==========================================

    # 迁移清单：每条记录格式 (目标版本, 描述, 迁移函数)
    # 迁移函数签名：fn(conn: sqlite3.Connection) -> None
    # 注意：函数内部禁止自行 commit/rollback，由引擎统一控制事务
    MIGRATIONS: list = []  # 在类体末尾通过 _register_migrations() 填充

    @classmethod
    def _register_migrations(cls):
        """注册所有版本迁移任务（按版本号升序排列）"""

        def migrate_v1_1(conn: sqlite3.Connection):
            """V1.0 -> V1.1：补齐扫描阶段新增字段"""
            cursor = conn.execute("PRAGMA table_info(tasks)")
            existing = {row[1] for row in cursor.fetchall()}
            columns_to_add = {
                "clean_name":       "TEXT",
                "season":           "INTEGER",
                "episode":          "INTEGER",
                "poster_path":      "TEXT",
                "local_poster_path": "TEXT",
            }
            for col, col_type in columns_to_add.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")
                    print(f"[INFO] [DB][V1.1] 新增字段: {col}")

        def migrate_v1_2(conn: sqlite3.Connection):
            """V1.1 -> V1.2：新增 is_active 字段，支持逻辑删除"""
            cursor = conn.execute("PRAGMA table_info(tasks)")
            existing = {row[1] for row in cursor.fetchall()}
            if "is_active" not in existing:
                conn.execute("ALTER TABLE tasks ADD COLUMN is_active INTEGER DEFAULT 1")
                print("[INFO] [DB][V1.2] 新增字段: is_active (逻辑删除支持)")

        def migrate_v1_3(conn: sqlite3.Connection):
            """V1.2 -> V1.3：新增 media_archive 归档表（任务流转冷存储）"""
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS media_archive (
                    id                INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_task_id  INTEGER,
                    path              TEXT NOT NULL,
                    file_name         TEXT,
                    clean_name        TEXT,
                    type              TEXT DEFAULT 'movie',
                    tmdb_id           TEXT,
                    imdb_id           TEXT,
                    title             TEXT,
                    year              TEXT,
                    target_path       TEXT,
                    season            INTEGER,
                    episode           INTEGER,
                    poster_path       TEXT,
                    local_poster_path TEXT,
                    sub_status        TEXT DEFAULT 'pending',
                    created_at        TEXT,
                    archived_at       DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_imdb_id ON media_archive (imdb_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_tmdb_id ON media_archive (tmdb_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_type ON media_archive (type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_media_archive_archived_at ON media_archive (archived_at)"
            )
            print("[INFO] [DB][V1.3] 新增表: media_archive (归档冷存储) + 4个索引")

        cls.MIGRATIONS = [
            ("1.1", "补齐扫描阶段字段 (clean_name/season/episode/poster_path/local_poster_path)", migrate_v1_1),
            ("1.2", "新增 is_active 字段（逻辑删除预留）", migrate_v1_2),
            ("1.3", "新增 media_archive 归档表（任务流转冷存储）", migrate_v1_3),
        ]

    def _init_database(self):
        """初始化数据库基础表结构（含 system_meta 元数据表）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()

            # ── 业务表：tasks ────────────────────────────────────────────
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT UNIQUE NOT NULL,
                    file_name TEXT,
                    clean_name TEXT,
                    type TEXT DEFAULT 'movie',
                    status TEXT DEFAULT 'pending',
                    tmdb_id TEXT,
                    imdb_id TEXT,
                    title TEXT,
                    year TEXT,
                    target_path TEXT,
                    sub_status TEXT DEFAULT 'pending',
                    last_sub_check TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    poster_path TEXT,
                    local_poster_path TEXT,
                    season INTEGER,
                    episode INTEGER,
                    is_active INTEGER DEFAULT 1
                )
                """
            )

            # ── 元数据表：system_meta（存储 schema_version 等系统级 KV）──
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS system_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )

            # 仅在首次创建时写入初始版本号（INSERT OR IGNORE 保证幂等）
            cursor.execute(
                "INSERT OR IGNORE INTO system_meta (key, value) VALUES ('schema_version', '1.0')"
            )

            conn.commit()
            print("[OK] [DB] 数据库初始化完成 (WAL 模式 + system_meta)")

    def _migrate_database(self):
        """
        原子化版本迁移引擎

        流程：
        1. 读取 system_meta 中的当前 schema_version
        2. 遍历 MIGRATIONS，执行所有版本号 > 当前版本的任务
        3. 每个迁移任务独占一个事务（BEGIN ... COMMIT / ROLLBACK）
        4. 迁移完成后更新 schema_version
        5. 任何迁移失败立即 rollback 并抛出异常，阻止系统启动
        """
        with self.db_lock:
            conn = self._get_conn()

            # ── 读取当前版本 ─────────────────────────────────────────────
            row = conn.execute(
                "SELECT value FROM system_meta WHERE key = 'schema_version'"
            ).fetchone()
            current_version = row[0] if row else "1.0"

            # ── 遍历迁移任务 ─────────────────────────────────────────────
            for target_version, description, migrate_fn in self.MIGRATIONS:
                # 版本比较：使用 tuple 数值比较，避免字符串排序陷阱
                def _ver(v: str):
                    return tuple(int(x) for x in v.split("."))

                if _ver(target_version) <= _ver(current_version):
                    continue  # 已完成的迁移跳过

                print(f"[INFO] [DB] 执行迁移 {current_version} -> {target_version}: {description}")

                try:
                    conn.execute("BEGIN")
                    migrate_fn(conn)
                    # 更新版本号（在同一事务内）
                    conn.execute(
                        "INSERT OR REPLACE INTO system_meta (key, value) VALUES ('schema_version', ?)",
                        (target_version,)
                    )
                    conn.commit()
                    current_version = target_version
                    print(f"[OK] [DB] 迁移完成，当前版本: {current_version}")

                except Exception as e:
                    conn.rollback()
                    error_msg = (
                        f"[FATAL] [DB] 迁移 {current_version} -> {target_version} 失败，"
                        f"已回滚。错误: {e}"
                    )
                    print(error_msg)
                    raise RuntimeError(error_msg) from e

    def _migrate_sensitive_keys(self):
        """自动迁移明文密钥到加密存储"""
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        settings = config.get("settings", {})
        crypto = get_crypto_manager()
        keys_to_migrate = {}
        for key in self.SENSITIVE_KEYS:
            value = settings.get(key, "")
            if value and value.strip():
                keys_to_migrate[key] = value
        if not keys_to_migrate:
            return
        secure_data = {}
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
        for key, value in keys_to_migrate.items():
            encrypted = crypto.encrypt_api_key(value)
            secure_data[key] = encrypted
            settings[key] = ""
        with open(self.secure_keys_path, "w", encoding="utf-8") as f:
            json.dump(secure_data, f, indent=4)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        print(f"[OK] [DB] 已迁移 {len(keys_to_migrate)} 个敏感密钥到加密存储")

    def _inject_ai_defaults(self):
        """
        灵魂注入：将 AI 规则注入为系统默认值，仅在字段为空时注入，避免覆盖用户自定义配置
        """
        DEFAULT_AI_NAME = "AI 智能助理"
        DEFAULT_AI_PERSONA = (
            "你是一个负责媒体归档的智能大脑。你必须直接输出结果，严禁说废话，严禁任何解释性语言。"
        )

        DEFAULT_EXPERT_ARCHIVE_RULES = (
            "核心任务：智能影视归档专家\n"
            "你负责将杂乱的影视文件路径清洗为标准的结构化数据。\n\n"
            "【标准数据契约 - 必须严格遵守】\n"
            "你必须输出 JSON 格式，包含以下字段：\n\n"
            "1. clean_name (字符串，必填)：\n"
            "   - 最通用、最纯净的作品名称\n"
            "   - 绝对禁止包含 4 位数年份\n"
            "   - 处理点号：必须将英文名中的点号替换为空格（例如 The.Legend.of.Hei.2 -> The Legend of Hei 2）\n"
            "   - 保留续集数字：务必保留名称后的数字（如 2, 3, Part II）\n\n"
            "2. chinese_title (字符串，可选)：\n"
            "   - 豆瓣/B站官方中文译名\n"
            "   - 如果原文件路径中包含清晰的中文片名，提取出来\n"
            "   - 如果没有中文，请务必留空！绝对不要尝试自己翻译英文片名！\n"
            "   - 知名IP翻译特权：如果你极其确定该英文是某部著名非英语作品的官方英文名（例如 Your Name 是《你的名字》，Spirited Away 是《千与千寻》），可以填入中文官方名称\n\n"
            "3. original_title (字符串，可选)：\n"
            "   - 原产地名称（日语原名、韩语原名等）\n"
            "   - 如果无法确定，留空\n\n"
            "4. year (字符串，可选)：\n"
            "   - 年份（4位数字）\n"
            "   - 如果无法确定，留空\n\n"
            "5. type (字符串，必填)：\n"
            "   - \"movie\" (电影)\n"
            "   - \"tv\" (剧集)\n"
            "   - \"IGNORE\" (纯广告/废片)\n\n"
            "6. season (整数，可选)：\n"
            "   - 季数（仅剧集需要）\n"
            "   - 如果是剧集但无法确定季数，默认为 1\n\n"
            "7. episode (整数，可选)：\n"
            "   - 集数（仅剧集需要）\n\n"
            "【剧集识别关键逻辑】\n"
            "遇到剧集时，必须确保 clean_name 是剧集名而非单集名：\n"
            "- 例如路径为 .../Attack on Titan/Season 3/S03E10 - Friends.mkv\n"
            "- 你绝对不能把单集片名（如 Friends）当成剧名！\n"
            "- 你必须从完整路径中提取父文件夹名称（如 Attack on Titan）作为 clean_name\n"
            "- 季集信息存入 season 和 episode 字段\n\n"
            "【广告与废片拦截】\n"
            "1. 含广告的电影（处理它）：\n"
            "   - 文件名如：[澳门首家]复仇者联盟4.mp4\n"
            "   - 提取：clean_name = \"复仇者联盟\" 或 \"Avengers Endgame\"，丢弃广告词\n"
            "   - type = \"movie\"\n"
            "2. 纯广告/废片（丢弃它）：\n"
            "   - 文件名如：澳门首家上线.mp4、最新地址发布.mkv\n"
            "   - 如果完全无法识别出任何影视剧名称，设置 type = \"IGNORE\"\n\n"
            "【输出示例】\n"
            '电影：{"clean_name": "Dune Part Two", "chinese_title": "沙丘2", "year": "2024", "type": "movie"}\n'
            '剧集：{"clean_name": "Attack on Titan", "chinese_title": "进击的巨人", "year": "2013", "type": "tv", "season": 3, "episode": 10}\n'
            '废片：{"clean_name": "", "type": "IGNORE"}'
        )

        DEFAULT_MASTER_ROUTER_RULES = (
            "角色设定：家庭媒体中心智能总控中枢\n\n"
            "【标准数据契约 - 统一键名规范】\n"
            "系统使用以下标准键名（所有模块必须遵守）：\n"
            "- clean_name: 纯净名（最通用名称，不含年份）\n"
            "- chinese_title: 中文官方译名（豆瓣/B站）\n"
            "- original_title: 原产地名称\n"
            "- year: 年份（4位数字字符串）\n"
            "- type: 类型（movie/tv/IGNORE）\n"
            "- season: 季（整数）\n"
            "- episode: 集（整数）\n\n"
            "【DOWNLOAD 指令增强规范】\n"
            "若意图为 DOWNLOAD，输出以下字段：\n"
            "- clean_name: 提取纯净片名。绝对不要包含年份数字。\n"
            "- type: \"movie\" (电影), \"tv\" (剧集), \"auto\" (未明确)。\n"
            "- year: 提取提到的年份，若无则填空字符串。"
        )
        from app.services.scraper.cleaner import MediaCleaner  # noqa: F401 保留导入供其他地方使用
        DEFAULT_FILENAME_CLEAN_REGEX = (
            "# 物理级正则去噪规则（Neon-Crate 工业默认，共15条）\n"
            "# 每行一条规则，支持 Python re 模块语法\n\n"
            "# 1. 分辨率标签过滤\n"
            r"\b(2160p|1080p|720p|480p|4k|8k|UHD|HD|SD|FHD|QHD|BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDRip|DVDRip|REMUX|HDTV|PDTV|DVDScr|CAM|TS|TC)\b" "\n\n"
            "# 2. 编码格式过滤\n"
            r"\b(x264|x265|H\.264|H\.265|HEVC|AVC|AV1|VP9|AAC|AC3|DTS|TrueHD|Atmos|FLAC|MP3|DD5\.1|DD\+|DTS-HD|MA|7\.1|5\.1|2\.0)\b" "\n\n"
            "# 3. 方括号技术标签过滤\n"
            r"\[[^\]]*?(?:Raws?|Sub|Team|Group|@|Lilith|DBD|Baha|bit|Audio|AAC|MP4|CHT|CHS|WEB|AVC|HEVC|x264|x265)[^\]]*?\]" "\n\n"
            "# 4. 花括号标签过滤\n"
            r"\{[^\}]+\}" "\n\n"
            "# 5. 广告词过滤\n"
            r"(澳门首家|最新地址|更多资源|高清下载|在线观看|www\.|http|\.com|\.net|\.org|\.cn|更多精彩|精彩推荐|免费下载|BT下载|磁力链接)" "\n\n"
            "# 6. 音频/视频特性标签过滤\n"
            r"\b(Dual\.Audio|Multi\.Audio|HDR|HDR10|HDR10\+|DV|Dolby\.Vision|10bit|10-bit|8bit|8-bit|SDR|HLG|IMAX|Extended|Unrated|Directors\.Cut|Remastered|3D|Half-SBS|Half-OU)\b" "\n\n"
            "# 7. 语言标签过滤\n"
            r"\b(中英|英中|简繁|繁简|国粤|粤语|国语|中字|英字|双语|双字|CHT|CHS|BIG5|GB|Mandarin|Cantonese)\b" "\n\n"
            "# 8. 制作组后缀过滤\n"
            r"-[A-Z0-9]+$" "\n\n"
            "# 9. 年份过滤\n"
            r"[\(\[\.\s]+(19\d{2}|20\d{2})[\)\]\.\s]+|\b(19\d{2}|20\d{2})\b" "\n\n"
            "# 10. 季集信息过滤-S01E01格式\n"
            r"[Ss](\d{1,2})[Ee](\d{1,3})" "\n\n"
            "# 11. 季集信息过滤-Season格式\n"
            r"[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee](?:pisode)?[\s\._-]*(\d{1,3})" "\n\n"
            "# 12. 季集信息过滤-1x01格式\n"
            r"(\d{1,2})x(\d{1,3})" "\n\n"
            "# 13. 季集信息过滤-EP01格式\n"
            r"[Ee][Pp]?[\s\._-]*(\d{1,3})" "\n\n"
            "# 14. 季集信息过滤-中文格式\n"
            r"第[\s\._-]*(\d{1,3})[\s\._-]*[集话話]" "\n\n"
            "# 15. 动漫番剧特殊格式\n"
            r"[-\s](\d{2,4})(?=\s*\[)" "\n"
        )
        injected_fields = []
        if not self.get_config("ai_name", "").strip():
            self.set_config("ai_name", DEFAULT_AI_NAME)
            injected_fields.append("ai_name")
        if not self.get_config("ai_persona", "").strip():
            self.set_config("ai_persona", DEFAULT_AI_PERSONA)
            injected_fields.append("ai_persona")
        if not self.get_config("expert_archive_rules", "").strip():
            self.set_config("expert_archive_rules", DEFAULT_EXPERT_ARCHIVE_RULES)
            injected_fields.append("expert_archive_rules")
        if not self.get_config("master_router_rules", "").strip():
            self.set_config("master_router_rules", DEFAULT_MASTER_ROUTER_RULES)
            injected_fields.append("master_router_rules")
        current_regex = self.get_config("filename_clean_regex", "").strip()
        if not current_regex:
            self.set_config("filename_clean_regex", DEFAULT_FILENAME_CLEAN_REGEX)
            injected_fields.append("filename_clean_regex")
        if injected_fields:
            print(f"[OK] [DB] 已注入 {len(injected_fields)} 个 AI 规则默认值")

    # ==========================================
    # 配置管理方法
    # ==========================================

    def get_config(self, key: str, default: Any = None) -> Any:
        """获取配置（敏感键自动解密）"""
        if not os.path.exists(self.config_path):
            return default
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        settings = config.get("settings", {})
        if key in self.SENSITIVE_KEYS:
            if os.path.exists(self.secure_keys_path):
                with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                    secure_data = json.load(f)
                encrypted = secure_data.get(key, "")
                if encrypted:
                    crypto = get_crypto_manager()
                    return crypto.decrypt_api_key(encrypted)
            return default
        return settings.get(key, default)

    def set_config(self, key: str, value: Any):
        """设置配置（敏感键自动加密）"""
        if not os.path.exists(self.config_path):
            config = {"settings": {}, "paths": []}
        else:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        if key in self.SENSITIVE_KEYS:
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
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if os.path.exists(self.secure_keys_path):
            with open(self.secure_keys_path, "r", encoding="utf-8") as f:
                secure_data = json.load(f)
            crypto = get_crypto_manager()
            for key in self.SENSITIVE_KEYS:
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
        for key in self.SENSITIVE_KEYS:
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

    # ==========================================
    # 路径管理方法
    # ==========================================

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
        """删除路径配置"""
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        paths = [p for p in config.get("paths", []) if p.get("id") != path_id]
        for i, p in enumerate(paths, 1):
            p["id"] = i
        config["paths"] = paths
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)

    # ==========================================
    # 任务管理方法
    # ==========================================

    def add_task(self, path: str, filename: str, clean_name: str, type_hint: str):
        """添加任务"""
        with self.db_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO tasks (path, file_name, clean_name, type, status) VALUES (?, ?, ?, ?, 'pending')",
                (path, filename, clean_name, type_hint)
            )
            conn.commit()

    def is_processed(self, file_path: str) -> bool:
        """检查文件是否已处理"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT 1 FROM tasks WHERE path = ? LIMIT 1", (file_path,))
            return cursor.fetchone() is not None

    def get_task_id_by_path(self, file_path: str) -> Optional[int]:
        """根据路径获取任务ID"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT id FROM tasks WHERE path = ? LIMIT 1", (file_path,))
            row = cursor.fetchone()
            return row[0] if row else None

    def get_task_status_by_path(self, file_path: str) -> Optional[str]:
        """根据路径获取任务状态"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT status FROM tasks WHERE path = ? LIMIT 1", (file_path,))
            row = cursor.fetchone()
            return row[0] if row else None

    def check_task_exists_by_path(self, file_path: str) -> bool:
        """检查指定路径的任务是否已存在（同时检查 tasks 和 media_archive 两张表）"""
        with self.db_lock:
            conn = self._get_conn()
            # 先查活跃任务表
            cursor = conn.execute("SELECT 1 FROM tasks WHERE path = ? LIMIT 1", (file_path,))
            if cursor.fetchone() is not None:
                return True
            # 再查归档表，防止已归档文件被重复扫描入库
            cursor = conn.execute("SELECT 1 FROM media_archive WHERE path = ? LIMIT 1", (file_path,))
            return cursor.fetchone() is not None

    def insert_task(self, task_data: Dict[str, Any]):
        """插入新任务记录"""
        with self.db_lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO tasks (path, file_name, clean_name, type, status, year, season, episode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_data.get("path"),
                    task_data.get("file_name"),
                    task_data.get("clean_name"),
                    task_data.get("type", "movie"),
                    task_data.get("status", "pending"),
                    task_data.get("year"),
                    task_data.get("season"),
                    task_data.get("episode")
                )
            )
            conn.commit()

    def update_task_status(
            self,
            task_id: int,
            status: Optional[str] = None,
            tmdb_id: Optional[str] = None,
            imdb_id: Optional[str] = None,
            target_path: Optional[str] = None,
            sub_status: Optional[str] = None,
            last_sub_check: Optional[str] = None,
            local_poster_path: Optional[str] = None,
            task_type: Optional[str] = None
    ):
        """更新任务状态"""
        with self.db_lock:
            conn = self._get_conn()
            updates = []
            params = []
            if status is not None:
                updates.append("status = ?"); params.append(status)
            if tmdb_id is not None:
                updates.append("tmdb_id = ?"); params.append(tmdb_id)
            if imdb_id is not None:
                updates.append("imdb_id = ?"); params.append(imdb_id)
            if target_path is not None:
                updates.append("target_path = ?"); params.append(target_path)
            if sub_status is not None:
                updates.append("sub_status = ?"); params.append(sub_status)
            if last_sub_check is not None:
                updates.append("last_sub_check = ?"); params.append(last_sub_check)
            if local_poster_path is not None:
                updates.append("local_poster_path = ?"); params.append(local_poster_path)
            if task_type is not None:
                updates.append("type = ?"); params.append(task_type)
            if updates:
                params.append(task_id)
                conn.execute(f"UPDATE tasks SET {chr(44).join(updates)} WHERE id = ?", params)
                conn.commit()
        if status == "archived":
            self.archive_task(task_id)

    def update_task_title_year(self, task_id: int, title: Optional[str] = None, year: Optional[str] = None, season: Optional[int] = None):
        """更新任务标题、年份和季号"""
        with self.db_lock:
            conn = self._get_conn()
            updates = []
            params = []
            if title is not None:
                updates.append("title = ?"); params.append(title)
            if year is not None:
                updates.append("year = ?"); params.append(year)
            if season is not None:
                updates.append("season = ?"); params.append(season)
            if updates:
                params.append(task_id)
                conn.execute(f"UPDATE tasks SET {chr(44).join(updates)} WHERE id = ?", params)
                conn.commit()

    def get_all_data(self, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取所有任务数据"""
        with self.db_lock:
            conn = self._get_conn()
            if search_keyword:
                cursor = conn.execute(
                    "SELECT id, path, file_name, clean_name, type, status, tmdb_id, imdb_id, title, year, target_path, sub_status, last_sub_check, created_at, poster_path, local_poster_path, season, episode FROM tasks WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ? ORDER BY created_at DESC",
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(
                    "SELECT id, path, file_name, clean_name, type, status, tmdb_id, imdb_id, title, year, target_path, sub_status, last_sub_check, created_at, poster_path, local_poster_path, season, episode FROM tasks ORDER BY created_at DESC"
                )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3],
                    "type": r[4], "status": r[5], "tmdb_id": r[6], "imdb_id": r[7],
                    "title": r[8], "year": r[9], "target_path": r[10],
                    "sub_status": r[11], "last_sub_check": r[12], "created_at": r[13],
                    "poster_path": r[14], "local_poster_path": r[15],
                    "season": r[16], "episode": r[17]
                }
                for r in rows
            ]

    def get_archived_data(self, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取 media_archive 表中的归档数据"""
        with self.db_lock:
            conn = self._get_conn()
            if search_keyword:
                cursor = conn.execute(
                    "SELECT id, path, file_name, clean_name, type, tmdb_id, imdb_id, title, year, target_path, sub_status, created_at, poster_path, local_poster_path, season, episode FROM media_archive WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ? ORDER BY archived_at DESC",
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(
                    "SELECT id, path, file_name, clean_name, type, tmdb_id, imdb_id, title, year, target_path, sub_status, created_at, poster_path, local_poster_path, season, episode FROM media_archive ORDER BY archived_at DESC"
                )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3],
                    "type": r[4], "status": "archived", "tmdb_id": r[5], "imdb_id": r[6],
                    "title": r[7], "year": r[8], "target_path": r[9],
                    "sub_status": r[10], "last_sub_check": None, "created_at": r[11],
                    "poster_path": r[12], "local_poster_path": r[13],
                    "season": r[14], "episode": r[15]
                }
                for r in rows
            ]

    def check_imdb_id_exists(self, imdb_id: str) -> bool:
        """检查 IMDB ID 是否已存在（仅统计已归档的）"""
        if not imdb_id or not str(imdb_id).strip():
            return False
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT 1 FROM media_archive WHERE imdb_id = ? LIMIT 1",
                (str(imdb_id).strip(),)
            )
            return cursor.fetchone() is not None

    def get_dashboard_stats(self) -> Dict[str, int]:
        """获取仪表盘统计数据"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE type = 'movie' AND status != 'failed'")
            movies = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE type = 'tv' AND status != 'failed'")
            tv_shows = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'pending'")
            pending = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE target_path IS NOT NULL AND target_path != ''")
            completed = cursor.fetchone()[0]
            return {"movies": movies, "tv_shows": tv_shows, "pending": pending, "completed": completed}

    def get_tasks_needing_scrape(self) -> List[Dict[str, Any]]:
        """获取需要刮削的任务列表（status=pending 且 tmdb_id 为空）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "SELECT id, path, file_name, clean_name, type, status, season, episode FROM tasks WHERE status = 'pending' AND (tmdb_id IS NULL OR tmdb_id = '') ORDER BY created_at ASC"
            )
            rows = cursor.fetchall()
            return [{"id": r[0], "path": r[1], "file_name": r[2], "clean_name": r[3], "type": r[4], "status": r[5], "season": r[6], "episode": r[7]} for r in rows]

    def get_tasks_needing_subtitles(self) -> List[Dict[str, Any]]:
        """获取需要字幕的任务列表（含 7 天冷却期过滤）"""
        with self.db_lock:
            conn = self._get_conn()
            from datetime import datetime, timedelta
            cooldown_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
            cursor = conn.execute(
                "SELECT id, path, file_name, type, tmdb_id, imdb_id, target_path, sub_status FROM media_archive WHERE tmdb_id IS NOT NULL AND tmdb_id != '' AND (sub_status IN ('pending', 'failed') OR sub_status IS NULL OR (sub_status = 'missing' AND (archived_at IS NULL OR archived_at < ?))) ORDER BY archived_at ASC",
                (cooldown_date,)
            )
            rows = cursor.fetchall()
            return [{"id": r[0], "path": r[1], "file_name": r[2], "type": r[3], "tmdb_id": r[4], "imdb_id": r[5], "target_path": r[6], "sub_status": r[7]} for r in rows]

    def get_active_library_path(self, media_type: str) -> str:
        """
        获取活动媒体库路径（1+1 绝对约束）
        """
        paths = self.get_managed_paths()
        active_libs = [p for p in paths if str(p.get("type", "")).strip().lower() in ["library", "media", "storage"] and p.get("enabled", True)]
        movie_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "movie"]
        tv_libs = [p for p in active_libs if str(p.get("category", "")).strip().lower() == "tv"]
        if len(movie_libs) > 1 or len(tv_libs) > 1:
            raise ValueError("[ERROR] [配置错误] 系统规定同时只能开启 1个电影媒体库 和 1个剧集媒体库！")
        if len(movie_libs) == 0:
            raise ValueError("[ERROR] [配置错误] 缺少处于开启状态的 Movie (电影) 媒体库！")
        if len(tv_libs) == 0:
            raise ValueError("[ERROR] [配置错误] 缺少处于开启状态的 TV (剧集) 媒体库！")
        media_type = str(media_type or "movie").strip().lower()
        if media_type == "movie":
            return os.path.abspath(movie_libs[0].get("path"))
        elif media_type == "tv":
            return os.path.abspath(tv_libs[0].get("path"))
        else:
            raise ValueError(f"未知的媒体类型: {media_type}")

    def get_agent_config(self, key: str = None, default: Any = None) -> Any:
        """获取 AI Agent 运行所需的完整配置"""
        config = self.get_all_config().get("settings", {})
        if key:
            return config.get(key, default)
        return {
            "provider": config.get("llm_provider", "cloud"),
            "cloud_url": config.get("llm_cloud_url", ""),
            "cloud_key": config.get("llm_cloud_key", ""),
            "cloud_model": config.get("llm_cloud_model", ""),
            "local_url": config.get("llm_local_url", ""),
            "local_key": config.get("llm_local_key", ""),
            "local_model": config.get("llm_local_model", ""),
            "ai_persona": config.get("ai_persona", ""),
            "expert_archive_rules": config.get("expert_archive_rules", ""),
            "master_router_rules": config.get("master_router_rules", ""),
            "ai_name": config.get("ai_name", "AI 影音大师")
        }

    # ==========================================
    # 归档方法
    # ==========================================

    def archive_task(self, task_id: int) -> bool:
        """
        原子事务归档单条任务
        前置条件：tasks 中对应记录 status 必须为 'archived'
        操作：将任务完整复制到 media_archive 表，然后物理删除 tasks 中的记录
        """
        with self.db_lock:
            conn = self._get_conn()
            row = conn.execute(
                """
                SELECT id, path, file_name, clean_name, type, tmdb_id, imdb_id,
                       title, year, target_path, season, episode,
                       poster_path, local_poster_path, sub_status, created_at, status
                FROM tasks WHERE id = ? LIMIT 1
                """,
                (task_id,)
            ).fetchone()
            if row is None:
                return False
            # 前置检查：仅归档 status='archived' 的记录
            if row[16] != "archived":
                return False
            try:
                conn.execute("BEGIN")
                conn.execute(
                    """
                    INSERT INTO media_archive (
                        original_task_id, path, file_name, clean_name, type,
                        tmdb_id, imdb_id, title, year, target_path,
                        season, episode, poster_path, local_poster_path,
                        sub_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        row[0],  row[1],  row[2],  row[3],  row[4],
                        row[5],  row[6],  row[7],  row[8],  row[9],
                        row[10], row[11], row[12], row[13],
                        row[14], row[15]
                    )
                )
                # 归档完成后物理删除 tasks 中的原始记录
                conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
                conn.commit()
                print(f"[OK] [DB] 任务已归档并从 tasks 移除。task_id={task_id}")
                return True
            except Exception as e:
                conn.rollback()
                print(f"[ERROR] [DB] archive_task 失败，已回滚。task_id={task_id}, 错误: {e}")
                raise

    def get_archive_data(self, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询归档历史记录"""
        with self.db_lock:
            conn = self._get_conn()
            if search_keyword:
                cursor = conn.execute(
                    """
                    SELECT id, task_id, path, file_name, clean_name, type,
                           tmdb_id, imdb_id, title, year, target_path,
                           season, episode, archived_at
                    FROM media_archive
                    WHERE file_name LIKE ? OR clean_name LIKE ? OR title LIKE ?
                    ORDER BY archived_at DESC
                    """,
                    (f"%{search_keyword}%", f"%{search_keyword}%", f"%{search_keyword}%")
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, original_task_id, path, file_name, clean_name, type,
                           tmdb_id, imdb_id, title, year, target_path,
                           season, episode, archived_at
                    FROM media_archive
                    ORDER BY archived_at DESC
                    """
                )
            rows = cursor.fetchall()
            return [
                {
                    "id": r[0], "original_task_id": r[1], "path": r[2], "file_name": r[3],
                    "clean_name": r[4], "type": r[5], "tmdb_id": r[6], "imdb_id": r[7],
                    "title": r[8], "year": r[9], "target_path": r[10],
                    "season": r[11], "episode": r[12], "archived_at": r[13]
                }
                for r in rows
            ]

    def get_archive_stats(self) -> Dict[str, int]:
        """归档统计：返回归档总数、电影数、剧集数"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media_archive")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE type = 'movie'")
            movies = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM media_archive WHERE type = 'tv'")
            tv_shows = cursor.fetchone()[0]
            return {"total": total, "movies": movies, "tv_shows": tv_shows}

    def update_archive_sub_status(self, archive_id: int, sub_status: str, last_check: Optional[str] = None) -> bool:
        """更新归档表中的字幕状态（字幕引擎写回专用）"""
        with self.db_lock:
            conn = self._get_conn()
            if last_check:
                conn.execute(
                    "UPDATE media_archive SET sub_status = ?, archived_at = ? WHERE id = ?",
                    (sub_status, last_check, archive_id)
                )
            else:
                conn.execute(
                    "UPDATE media_archive SET sub_status = ? WHERE id = ?",
                    (sub_status, archive_id)
                )
            conn.commit()
            return True

    # ==========================================
    # 任务删除方法
    # ==========================================

    def delete_tasks_by_ids(self, ids: List[int]):
        """批量删除任务记录（同时清理 media_archive）"""
        if not ids:
            return
        with self.db_lock:
            conn = self._get_conn()
            placeholders = chr(44).join(["?"] * len(ids))
            # 先收集 tasks 表中对应记录的 path，用于匹配 media_archive
            rows = conn.execute(f"SELECT path FROM tasks WHERE id IN ({placeholders})", ids).fetchall()
            paths = [r[0] for r in rows if r[0]]
            conn.execute(f"DELETE FROM tasks WHERE id IN ({placeholders})", ids)
            # media_archive 按 path 删除（id 是独立自增，不与 tasks.id 对应）
            if paths:
                path_placeholders = chr(44).join(["?"] * len(paths))
                conn.execute(f"DELETE FROM media_archive WHERE path IN ({path_placeholders})", paths)
            # 兜底：同时按 original_task_id 删除
            conn.execute(f"DELETE FROM media_archive WHERE original_task_id IN ({placeholders})", ids)
            conn.commit()

    def delete_task(self, task_id: int) -> bool:
        """删除单条任务记录（同时清理 media_archive）"""
        with self.db_lock:
            conn = self._get_conn()
            # 先获取 path 用于匹配 media_archive（media_archive.id 与 tasks.id 不同）
            row = conn.execute("SELECT path FROM tasks WHERE id = ?", (task_id,)).fetchone()
            path = row[0] if row else None
            cur1 = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            # 按 path 删除 media_archive（最准确）
            cur2_count = 0
            if path:
                cur2 = conn.execute("DELETE FROM media_archive WHERE path = ?", (path,))
                cur2_count = cur2.rowcount
            # 兜底：按 original_task_id 删除
            cur3 = conn.execute("DELETE FROM media_archive WHERE original_task_id = ?", (task_id,))
            conn.commit()
            return (cur1.rowcount + cur2_count + cur3.rowcount) > 0

    def clear_all_tasks(self) -> int:
        """清空所有任务记录（核弹按钮，同时清空 media_archive）"""
        with self.db_lock:
            conn = self._get_conn()
            cursor = conn.execute("SELECT COUNT(*) FROM tasks")
            count_tasks = cursor.fetchone()[0]
            cursor = conn.execute("SELECT COUNT(*) FROM media_archive")
            count_archive = cursor.fetchone()[0]
            count = count_tasks + count_archive
            conn.execute("DELETE FROM tasks")
            conn.execute("DELETE FROM media_archive")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='tasks'")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='media_archive'")
            conn.commit()
            print(f"[OK] [DB] 已清空任务表，删除 {count} 条记录，自增 ID 已重置")
            return count

    def reset_settings_to_defaults(self, target: str):
        """重置配置为工业级默认值，target: ai 或 regex"""
        target = str(target).strip().lower()
        if target == "ai":
            DEFAULT_AI_PERSONA = "你是一个负责媒体归档的智能大脑。你必须直接输出结果，严禁说废话，严禁任何解释性语言。"

            DEFAULT_EXPERT_ARCHIVE_RULES = (
                "核心任务：智能影视归档专家\n"
                "你负责将杂乱的影视文件路径清洗为标准的结构化数据。\n\n"
                "【标准数据契约 - 必须严格遵守】\n"
                "你必须输出 JSON 格式，包含以下字段：\n\n"
                "1. clean_name (字符串，必填)：\n"
                "   - 最通用、最纯净的作品名称\n"
                "   - 绝对禁止包含 4 位数年份\n"
                "   - 处理点号：必须将英文名中的点号替换为空格（例如 The.Legend.of.Hei.2 -> The Legend of Hei 2）\n"
                "   - 保留续集数字：务必保留名称后的数字（如 2, 3, Part II）\n\n"
                "2. chinese_title (字符串，可选)：\n"
                "   - 豆瓣/B站官方中文译名\n"
                "   - 如果没有中文，请务必留空！绝对不要尝试自己翻译英文片名！\n"
                "   - 知名IP翻译特权：如果你极其确定该英文是某部著名非英语作品的官方英文名（例如 Your Name 是《你的名字》），可以填入中文官方名称\n\n"
                "3. original_title (字符串，可选)：原产地名称（日语原名、韩语原名等），无法确定则留空\n\n"
                "4. year (字符串，可选)：年份（4位数字），无法确定则留空\n\n"
                "5. type (字符串，必填)：\"movie\" / \"tv\" / \"IGNORE\"\n\n"
                "6. season (整数，可选)：季数（仅剧集需要，默认为 1）\n\n"
                "7. episode (整数，可选)：集数（仅剧集需要）\n\n"
                "【剧集识别关键逻辑】\n"
                "从完整路径中提取父文件夹名称作为 clean_name，季集信息存入 season 和 episode 字段。\n\n"
                "【广告与废片拦截】\n"
                "如果完全无法识别出任何影视剧名称，设置 type = \"IGNORE\"\n\n"
                "【输出示例】\n"
                '电影：{"clean_name": "Dune Part Two", "chinese_title": "沙丘2", "year": "2024", "type": "movie"}\n'
                '剧集：{"clean_name": "Attack on Titan", "chinese_title": "进击的巨人", "year": "2013", "type": "tv", "season": 3, "episode": 10}\n'
                '废片：{"clean_name": "", "type": "IGNORE"}'
            )

            DEFAULT_MASTER_ROUTER_RULES = (
                "你是家庭媒体中心智能总控中枢，负责识别用户指令意图并输出标准 JSON。\n\n"
                "【支持的意图列表】\n"
                "- ACTION_SCAN：扫描新文件（关键词：扫描、发现、新文件、找新片）\n"
                "- ACTION_SCRAPE：刮削元数据（关键词：刮削、整理、元数据、更新信息）\n"
                "- ACTION_SUBTITLE：补全字幕（关键词：字幕、subtitle、补全）\n"
                "- SYSTEM_STATUS：查询系统状态（关键词：状态、汇报、战况、日志、统计）\n"
                "- DOWNLOAD：下载影片（关键词：下载、想看、找片、帮我找）\n"
                "- LOCAL_SEARCH：本地库搜索（关键词：本地、库里、有没有）\n"
                "- CHAT：普通闲聊（不符合以上任何意图）\n\n"
                "【输出规则 - 必须严格遵守】\n"
                "1. 你必须且只能输出一个 JSON 对象，禁止输出任何其他文字\n"
                '2. 普通指令格式：{"intent": "ACTION_SCAN"}\n'
                '3. DOWNLOAD 指令格式：{"intent": "DOWNLOAD", "clean_name": "中文片名", "en_name": "英文片名", "type": "movie", "year": ""}\n'
                "   - clean_name：中文片名（如\"美国队长\"）\n"
                "   - en_name：你知道的英文片名（如\"Captain America: The First Avenger\"），不确定则留空\n"
                "   - 若用户说\"第一部\"\"1\"等序号，必须保留在 clean_name 和 en_name 中\n"
                "   - 若用户说\"第二部\"，转换为数字2，en_name 对应第2部的英文名\n"
                '4. 不确定时统一返回：{"intent": "CHAT"}\n\n'
                "【示例】\n"
                '用户：扫描新文件 → {"intent": "ACTION_SCAN"}\n'
                '用户：汇报战况 → {"intent": "SYSTEM_STATUS"}\n'
                '用户：我想看美国队长1 → {"intent": "DOWNLOAD", "clean_name": "美国队长 1", "en_name": "Captain America: The First Avenger", "type": "movie", "year": "2011"}\n'
                '用户：下载美国队长第二部 → {"intent": "DOWNLOAD", "clean_name": "美国队长 2", "en_name": "Captain America: The Winter Soldier", "type": "movie", "year": "2014"}\n'
                '用户：今天天气真好 → {"intent": "CHAT"}'
            )

            self.set_config("ai_name", "AI 智能助理")
            self.set_config("ai_persona", DEFAULT_AI_PERSONA)
            self.set_config("expert_archive_rules", DEFAULT_EXPERT_ARCHIVE_RULES)
            self.set_config("master_router_rules", DEFAULT_MASTER_ROUTER_RULES)
            print("[OK] [DB] AI 规则已重置为工业级默认值")
        elif target == "regex":
            regex_str = (
                "# 物理级正则去噪规则（Neon-Crate 工业默认，共15条）\n"
                "# 每行一条规则，支持 Python re 模块语法\n\n"
                "# 1. 分辨率标签过滤\n"
                r"\b(2160p|1080p|720p|480p|4k|8k|UHD|HD|SD|FHD|QHD|BluRay|BDRip|BRRip|WEB-DL|WEBRip|HDRip|DVDRip|REMUX|HDTV|PDTV|DVDScr|CAM|TS|TC)\b" "\n\n"
                "# 2. 编码格式过滤\n"
                r"\b(x264|x265|H\.264|H\.265|HEVC|AVC|AV1|VP9|AAC|AC3|DTS|TrueHD|Atmos|FLAC|MP3|DD5\.1|DD\+|DTS-HD|MA|7\.1|5\.1|2\.0)\b" "\n\n"
                "# 3. 方括号技术标签过滤\n"
                r"\[[^\]]*?(?:Raws?|Sub|Team|Group|@|Lilith|DBD|Baha|bit|Audio|AAC|MP4|CHT|CHS|WEB|AVC|HEVC|x264|x265)[^\]]*?\]" "\n\n"
                "# 4. 花括号标签过滤\n"
                r"\{[^\}]+\}" "\n\n"
                "# 5. 广告词过滤\n"
                r"(澳门首家|最新地址|更多资源|高清下载|在线观看|www\.|http|\.com|\.net|\.org|\.cn|更多精彩|精彩推荐|免费下载|BT下载|磁力链接)" "\n\n"
                "# 6. 音频/视频特性标签过滤\n"
                r"\b(Dual\.Audio|Multi\.Audio|HDR|HDR10|HDR10\+|DV|Dolby\.Vision|10bit|10-bit|8bit|8-bit|SDR|HLG|IMAX|Extended|Unrated|Directors\.Cut|Remastered|3D|Half-SBS|Half-OU)\b" "\n\n"
                "# 7. 语言标签过滤\n"
                r"\b(中英|英中|简繁|繁简|国粤|粤语|国语|中字|英字|双语|双字|CHT|CHS|BIG5|GB|Mandarin|Cantonese)\b" "\n\n"
                "# 8. 制作组后缀过滤\n"
                r"-[A-Z0-9]+$" "\n\n"
                "# 9. 年份过滤\n"
                r"[\(\[\.\s]+(19\d{2}|20\d{2})[\)\]\.\s]+|\b(19\d{2}|20\d{2})\b" "\n\n"
                "# 10. 季集信息过滤-S01E01格式\n"
                r"[Ss](\d{1,2})[Ee](\d{1,3})" "\n\n"
                "# 11. 季集信息过滤-Season格式\n"
                r"[Ss]eason[\s\._-]*(\d{1,2})[\s\._-]*[Ee](?:pisode)?[\s\._-]*(\d{1,3})" "\n\n"
                "# 12. 季集信息过滤-1x01格式\n"
                r"(\d{1,2})x(\d{1,3})" "\n\n"
                "# 13. 季集信息过滤-EP01格式\n"
                r"[Ee][Pp]?[\s\._-]*(\d{1,3})" "\n\n"
                "# 14. 季集信息过滤-中文格式\n"
                r"第[\s\._-]*(\d{1,3})[\s\._-]*[集话話]" "\n\n"
                "# 15. 动漫番剧特殊格式\n"
                r"[-\s](\d{2,4})(?=\s*\[)" "\n"
            )
            self.set_config("filename_clean_regex", regex_str)
            print("[OK] [DB] 正则清洗规则已重置为工业级默认值（15条规则）")
        else:
            raise ValueError(f"[ERROR] target 必须为 'ai' 或 'regex'，收到: {target}")

    def _save_config(self):
        """内部方法：持久化配置到磁盘"""
        if not os.path.exists(self.config_path):
            return
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        tmp_path = self.config_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.config_path)


# 全局单例
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager
