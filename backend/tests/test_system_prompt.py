"""
System Prompt 注入测试脚本
用于验证 master_router_rules 和 ai_persona 是否正确注入到 LLM 调用中
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from app.core.database import DatabaseManager
from app.services.ai.agent import AIAgent


async def test_system_prompt_injection():
    """测试 System Prompt 是否正确注入"""
    print("=" * 60)
    print("System Prompt 注入测试")
    print("=" * 60)
    
    # 初始化数据库和 AI Agent
    db = DatabaseManager()
    agent = AIAgent(db)
    
    # 第一步：检查配置是否存在
    print("\n[步骤 1] 检查数据库配置...")
    router_rules = db.get_agent_config("master_router_rules", "")
    ai_persona = db.get_agent_config("ai_persona", "")
    
    print(f"✓ master_router_rules 长度: {len(router_rules)} 字符")
    print(f"✓ ai_persona 长度: {len(ai_persona)} 字符")
    
    if router_rules:
        print(f"✓ master_router_rules 前 100 字符: {router_rules[:100]}...")
    else:
        print("⚠ master_router_rules 为空！")
    
    if ai_persona:
        print(f"✓ ai_persona 前 100 字符: {ai_persona[:100]}...")
    else:
        print("⚠ ai_persona 为空！")
    
    # 第二步：测试意图识别
    print("\n[步骤 2] 测试意图识别...")
    test_messages = [
        "扫描新文件",
        "下载电影 庆余年",
        "系统状态",
        "你好"
    ]
    
    for msg in test_messages:
        print(f"\n测试消息: '{msg}'")
        try:
            response, action_code = await agent.process_message(msg)
            print(f"  → 意图代码: {action_code}")
            print(f"  → AI 响应: {response[:100]}...")
        except Exception as e:
            print(f"  ✗ 错误: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_system_prompt_injection())
