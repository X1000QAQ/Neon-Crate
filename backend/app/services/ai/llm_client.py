"""
LLM 客户端 - 双引擎支持（云端 API + 本地 Ollama）

功能：
1. 云端 API 支持（OpenAI/DeepSeek 兼容接口）
2. 本地 Ollama 支持
3. 自动重试机制
4. 统一的调用接口
"""
import httpx
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LLMClient:
    """LLM 客户端 - 统一的 LLM 调用接口"""
    
    def __init__(self, db_manager):
        """
        初始化 LLM 客户端
        
        Args:
            db_manager: DatabaseManager 实例，用于读取配置
        """
        self.db = db_manager
        logger.info("✅ [LLM] 客户端已初始化")
    
    async def call_llm(
        self, 
        system_prompt: str, 
        user_prompt: str, 
        retries: int = 3,
        temperature: float = 0.1
    ) -> str:
        """
        调用 LLM 生成响应（带重试机制）
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            retries: 重试次数
            temperature: 温度参数
            
        Returns:
            str: LLM 响应文本
        """
        # 从数据库读取 LLM 配置
        provider = self.db.get_config("llm_provider", "cloud")
        api_url = self.db.get_config(f"llm_{provider}_url")
        api_key = self.db.get_config(f"llm_{provider}_key")
        model = self.db.get_config(f"llm_{provider}_model")
        
        if not api_url or not api_key:
            error_msg = f"error: 缺失 {provider} 配置"
            logger.error(f"❌ [LLM] {error_msg}")
            return error_msg
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": temperature,
            "enable_thinking": False,   # 关闭 Qwen3 思考模式，避免输出污染 JSON 解析
        }
        
        # 本地模型 timeout 更长，重试次数更少；云端保持原有配置
        is_local = (provider == "local")
        effective_timeout = 180.0 if is_local else 60.0  # 本地 14B 推理最长 3 分钟
        effective_retries = 1 if is_local else retries    # 本地不重试，失败直接降级
        
        # 三连击重试机制
        for attempt in range(effective_retries):
            try:
                async with httpx.AsyncClient(follow_redirects=True) as client:
                    resp = await client.post(
                        api_url, 
                        headers=headers, 
                        json=payload, 
                        timeout=effective_timeout
                    )
                    resp.raise_for_status()
                    result = resp.json()['choices'][0]['message']['content'].strip()
                    logger.info(f"✅ [LLM] {provider} 引擎响应成功")
                    return result
                    
            except Exception as e:
                logger.warning(
                    f"⚠️ [LLM] 通讯波动 (第 {attempt + 1}/{effective_retries} 次尝试): {str(e)}"
                )
                if attempt < effective_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # 指数退避
                else:
                    error_msg = f"error: {str(e)}"
                    logger.error(f"❌ [LLM] 最终失败: {error_msg}")
                    return error_msg
