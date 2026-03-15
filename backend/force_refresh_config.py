#!/usr/bin/env python3
"""
强力配置刷新脚本

功能：
1. 强制更新数据库中的 master_router_rules
2. 强制更新数据库中的 ai_persona（包含绝对沟通法则）
3. 验证配置是否包含语义净化规则
4. 清除所有缓存状态

使用方法：
    python force_refresh_config.py
"""
import sys
from pathlib import Path

backend_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(backend_dir))

from app.infra.database.db_manager import get_db_manager
from app.infra.database.default_config import DEFAULT_CONFIG

def main():
    print("🔄 开始强力刷新配置...")
    
    db = get_db_manager()
    
    # 1. 强制更新 master_router_rules
    new_rules = DEFAULT_CONFIG.get("master_router_rules", "")
    db.set_config("master_router_rules", new_rules)
    print(f"✅ master_router_rules 已更新（{len(new_rules)} 字符）")
    
    # 2. 强制更新 ai_persona（包含绝对沟通法则）
    new_persona = DEFAULT_CONFIG.get("ai_persona", "")
    db.set_config("ai_persona", new_persona)
    print(f"✅ ai_persona 已更新（{len(new_persona)} 字符）")
    
    # 3. 强制更新 ai_name
    new_name = DEFAULT_CONFIG.get("ai_name", "")
    db.set_config("ai_name", new_name)
    print(f"✅ ai_name 已更新: {new_name}")
    
    # 4. 清除候选状态
    db.set_config("_pending_candidates", "")
    print("✅ 候选状态已清除")
    
    # 5. 清除下载元数据
    db.set_config("_pending_download_meta", "")
    print("✅ 下载元数据已清除")
    
    # 6. 验证语义净化规则
    print("\n📋 验证语义净化规则...")
    master_router_rules = db.get_config("master_router_rules", "")
    has_reply_purity = "reply 字段纯净性" in master_router_rules
    has_json_ban = "严禁在 reply 中嵌套 JSON" in master_router_rules
    
    if has_reply_purity and has_json_ban:
        print("✅ master_router_rules 语义净化规则已生效")
    else:
        print("⚠️ master_router_rules 语义净化规则未找到")
    
    # 7. 验证绝对沟通法则
    ai_persona = db.get_config("ai_persona", "")
    has_communication_law = "绝对沟通法则" in ai_persona
    has_json_ban_persona = "严禁在对话中使用任何 JSON 结构" in ai_persona
    
    if has_communication_law and has_json_ban_persona:
        print("✅ ai_persona 绝对沟通法则已生效")
    else:
        print("⚠️ ai_persona 绝对沟通法则未找到")
    
    print("\n✅ 强力刷新完成！请重启后端服务使配置生效。")
    print("\n📋 配置摘要:")
    print(f"  - AI 名称: {new_name}")
    print(f"  - AI 人格长度: {len(new_persona)} 字符")
    print(f"  - 路由规则长度: {len(new_rules)} 字符")

if __name__ == "__main__":
    main()
