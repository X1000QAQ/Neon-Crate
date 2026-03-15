#!/usr/bin/env python3
"""
配置强制刷新脚本

功能：强制更新数据库中的 master_router_rules，使新的人格准则立即生效

使用方法：
    python refresh_config.py
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.infra.database.db_manager import get_db_manager
from app.infra.database.default_config import DEFAULT_CONFIG

def main():
    """强制刷新配置"""
    print("🔄 开始刷新配置...")
    
    db = get_db_manager()
    
    # 强制更新 master_router_rules
    new_rules = DEFAULT_CONFIG.get("master_router_rules", "")
    db.set_config("master_router_rules", new_rules)
    print("✅ master_router_rules 已更新")
    
    # 强制更新 ai_persona
    new_persona = DEFAULT_CONFIG.get("ai_persona", "")
    db.set_config("ai_persona", new_persona)
    print("✅ ai_persona 已更新")
    
    # 强制更新 ai_name
    new_name = DEFAULT_CONFIG.get("ai_name", "")
    db.set_config("ai_name", new_name)
    print("✅ ai_name 已更新")
    
    # 验证更新
    print("\n📋 验证配置...")
    print(f"AI 名称: {db.get_config('ai_name', '')}")
    print(f"路由规则长度: {len(db.get_config('master_router_rules', ''))} 字符")
    print(f"人格描述长度: {len(db.get_config('ai_persona', ''))} 字符")
    
    print("\n✅ 配置刷新完成！新的人格准则已生效。")

if __name__ == "__main__":
    main()
