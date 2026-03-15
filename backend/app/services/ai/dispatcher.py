"""
逻辑分发器（Dispatcher）

设计目标：
  实现「意图」与「执行」的物理隔离
  所有 AI 产生的指令必须经过此分发器完成参数校验与频率管控

在 AI 控制链路中的定位：
  协议校验层：llm_client.py     - force_json 强制结构化输出
  逻辑分发层：dispatcher.py    - 白名单校验 + 参数强校验（本文件）
  人工授权机制：前端 ActionConfirmCard - 用户显式授权后才触发执行

核心职责：
  1. AIActionEnum   白名单枚举：非白名单 action 直接丢弃
  2. AIIntentModel  Pydantic 强校验：对 LLM 提取的参数进行类型与长度校验
  3. Dispatcher     物理校验 + 频率管控：片名合法性、年份格式、操作冷却限制

使用方式：
  from app.services.ai.dispatcher import Dispatcher, AIActionEnum, AIIntentModel

  # 校验 LLM 返回的原始 dict
  result = Dispatcher.validate_intent(raw_dict)
  if result is None:
      # 校验未通过，已记录日志，调用方直接返回错误提示
      ...
"""
import re
import time
import logging
from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════
# 白名单枚举层：AIActionEnum - 合法意图注册表
# ══════════════════════════════════════════════════════════════════

class AIActionEnum(str, Enum):
    """
    AI 意图白名单枚举
    
    非此枚举内的 action 将在解析层被直接丢弃，
    不会传递到任何执行逻辑。
    
    维护规则：
    - 新增意图必须同步在此枚举中注册
    - 已废弃意图直接从枚举中删除（自动阻断）
    """
    ACTION_SCAN     = "ACTION_SCAN"      # 物理扫描
    ACTION_SCRAPE   = "ACTION_SCRAPE"    # 全量刮削
    ACTION_SUBTITLE = "ACTION_SUBTITLE"  # 字幕补全
    DOWNLOAD        = "DOWNLOAD"         # 下载影片
    LOCAL_SEARCH    = "LOCAL_SEARCH"     # 本地搜索
    SYSTEM_STATUS   = "SYSTEM_STATUS"    # 系统状态查询
    CHAT            = "CHAT"             # 普通闲聊


# ══════════════════════════════════════════════════════════════════
# 参数校验层：AIIntentModel - LLM 输出的 Pydantic 强类型约束
# ══════════════════════════════════════════════════════════════════

class AIIntentModel(BaseModel):
    """
    AI 意图参数 Pydantic 强校验模型
    
    对 LLM 提取的参数进行类型和长度强校验：
    - intent:     必须是 AIActionEnum 白名单内的值
    - reply:      AI 回复文本，限制最大长度防止超长输出
    - clean_name: 片名，限制长度防止注入
    - en_name:    英文片名，限制长度
    - year:       年份，强制 4 位数字格式或空字符串
    - media_type: 类型，枚举限制（movie/tv）
    """
    intent: AIActionEnum = AIActionEnum.CHAT
    reply: str = Field("", max_length=1000, description="AI 回复文本")
    
    # DOWNLOAD 专用字段
    clean_name: str = Field("", max_length=100, description="中文片名")
    en_name:    str = Field("", max_length=100, description="英文片名")
    year:       str = Field("", description="年份（4位数字或空）")
    media_type: str = Field("movie", description="类型：movie/tv")
    
    @field_validator("year")
    @classmethod
    def validate_year(cls, v: str) -> str:
        """年份必须为 4 位数字或空字符串"""
        if v and not re.fullmatch(r'\d{4}', v.strip()):
            logger.warning(f"[Dispatcher] 非法年份已过滤: {repr(v)}")
            return ""  # 非法年份静默清除，不抛出异常
        return v.strip()
    
    @field_validator("media_type")
    @classmethod
    def validate_media_type(cls, v: str) -> str:
        """类型必须为 movie 或 tv，其他值归一化为 movie"""
        if v.lower() not in ("movie", "tv"):
            logger.warning(f"[Dispatcher] 非法 media_type 已归一化: {repr(v)} -> 'movie'")
            return "movie"
        return v.lower()
    
    @field_validator("clean_name", "en_name")
    @classmethod
    def strip_fields(cls, v: str) -> str:
        """去除首尾空白"""
        return v.strip()


# ══════════════════════════════════════════════════════════════════
# 指令分发层：Dispatcher - 物理校验 + 频率管控
# ══════════════════════════════════════════════════════════════════

class Dispatcher:
    """
    AI 指令逻辑分发器
    
    所有 AI 产生的指令必须经过此分发器进行物理校验，
    才能传递到真正的执行层（BackgroundTasks / ServarrClient）。
    
    物理校验规则：
    - DOWNLOAD：片名不能为空
    - ACTION_SCAN/SCRAPE/SUBTITLE：检查频率限制（60 秒冷却）
    
    频率限制说明：
    - 使用内存字典记录上次执行时间
    - 进程重启后自动重置（无持久化，轻量设计）
    - 防止 AI 误判循环触发相同指令
    """
    
    # 频率限制：记录上次各类操作的触发时间
    _last_trigger: dict = {}
    _COOLDOWN_SECONDS = 5  # 同类操作最小间隔 5 秒
    
    @classmethod
    def validate_intent(cls, raw: dict) -> Optional[AIIntentModel]:
        """
        校验 LLM 返回的原始字典，返回强类型模型

        校验流程：
        1. Pydantic 类型校验（白名单意图、年份格式、字段长度）
        2. 业务合法性校验（DOWNLOAD 意图要求片名非空）
        3. 操作频率管控（只读检查，不写入时间戳）

        Args:
            raw: LLM 返回并经过 _parse_json_response 解析的原始字典

        Returns:
            AIIntentModel: 校验通过的意图模型
            None:          校验未通过，调用方应返回错误提示
        """
        if not raw or not isinstance(raw, dict):
            logger.warning("[Dispatcher] 收到空/非法输入，已丢弃")
            return None
        
        # ── 参数合法性校验（Pydantic）──────────────────────────────
        try:
            model = AIIntentModel(**raw)
        except Exception as e:
            logger.error(f"[Dispatcher] Pydantic 校验失败: {e} | 原始数据: {raw}")
            return None
        
        # ── 业务合法性校验（片名非空）────────────────────────────────
        if model.intent == AIActionEnum.DOWNLOAD:
            if not model.clean_name and not model.en_name:
                logger.warning("[Dispatcher] DOWNLOAD 意图片名为空，已拦截")
                return None
        
        # ── 操作频率管控（只读检查，不写时间戳）────────────────────────
        # 时间戳写入由 record_execution() 在任务真正触发时负责
        # validate_intent 本身不产生任何持久化副作用
        rate_limited_actions = {
            AIActionEnum.ACTION_SCAN,
            AIActionEnum.ACTION_SCRAPE,
            AIActionEnum.ACTION_SUBTITLE,
        }
        if model.intent in rate_limited_actions:
            now = time.time()
            last = cls._last_trigger.get(model.intent, 0)
            elapsed = now - last
            if elapsed < cls._COOLDOWN_SECONDS:
                remaining = int(cls._COOLDOWN_SECONDS - elapsed)
                logger.warning(
                    f"[Dispatcher] 频率限制触发: {model.intent} 上次执行 {int(elapsed)}s 前，"
                    f"冷却剩余 {remaining}s，已拦截"
                )
                return None
            # 不在此处写入时间戳，由 record_execution() 在任务触发时写入
        
        logger.info(f"[Dispatcher] ✅ 校验通过: intent={model.intent}, "
                    f"clean_name={repr(model.clean_name)}, year={repr(model.year)}, "
                    f"media_type={repr(model.media_type)}")
        return model

    @classmethod
    def check_cooldown(cls, action: AIActionEnum) -> tuple[bool, int]:
        """
        只读检查指定意图是否处于操作冷却期（不写入时间戳，无副作用）

        用于 /chat 端点在返回待确认卡片前进行频率预检。
        预检本身不消耗冷却时间；冷却计时由 record_execution() 负责。

        Args:
            action: 要检查的意图枚举值

        Returns:
            (is_cooling, remaining_seconds)
            is_cooling=True  表示仍在冷却中，remaining_seconds 为剩余秒数
            is_cooling=False 表示可以执行，remaining_seconds=0
        """
        rate_limited_actions = {
            AIActionEnum.ACTION_SCAN,
            AIActionEnum.ACTION_SCRAPE,
            AIActionEnum.ACTION_SUBTITLE,
        }
        if action not in rate_limited_actions:
            return False, 0
        now = time.time()
        last = cls._last_trigger.get(action, 0)
        elapsed = now - last
        if elapsed < cls._COOLDOWN_SECONDS:
            remaining = int(cls._COOLDOWN_SECONDS - elapsed)
            return True, remaining
        return False, 0

    @classmethod
    def record_execution(cls, action: AIActionEnum) -> None:
        """
        记录任务真正开始执行的时间，启动操作冷却计时。

        冷却时间从用户授权执行时开始计算，而非从 AI 意图识别时计算。
        用户点击「取消」不会触发此方法，因此不消耗冷却时间。

        调用时机：在 /confirm 端点 background_tasks.add_task() 之后显式调用。

        Args:
            action: 已授权执行的意图枚举值
        """
        cls._last_trigger[action] = time.time()
        logger.info(f"[Dispatcher] 冷却计时开始: {action}，冷却 {cls._COOLDOWN_SECONDS}s")

    @classmethod
    def reset_cooldown(cls, action: AIActionEnum) -> None:
        """
        手动重置某个意图的冷却时间（测试 / 管理员用途）

        Args:
            action: 要重置的意图枚举值
        """
        cls._last_trigger.pop(action, None)
        logger.info(f"[Dispatcher] 冷却已重置: {action}")
