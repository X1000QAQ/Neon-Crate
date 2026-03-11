"""
字幕功能测试脚本

测试步骤：
1. 检查数据库配置（os_api_key, os_user_agent）
2. 查询需要字幕的任务
3. 手动触发字幕下载
4. 验证字幕文件是否生成
5. 验证数据库 sub_status 是否更新
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from app.infra.database import get_db_manager
from app.services.subtitle import SubtitleEngine


async def test_subtitle_download():
    """测试字幕下载功能"""
    print("=" * 60)
    print("字幕功能测试")
    print("=" * 60)
    
    # 1. 获取数据库管理器
    db = get_db_manager()
    print("\n✅ 数据库管理器初始化成功")
    
    # 2. 检查配置
    api_key = db.get_config("os_api_key", "").strip()
    user_agent = db.get_config("os_user_agent", "SubtitleHunter/13.2")
    
    print(f"\n📋 配置检查:")
    print(f"  - API Key: {'已配置' if api_key else '❌ 未配置'}")
    print(f"  - User Agent: {user_agent}")
    
    if not api_key:
        print("\n❌ 错误: 未配置 OpenSubtitles API Key")
        print("请在系统设置中配置 os_api_key")
        return
    
    # 3. 查询需要字幕的任务
    tasks = db.get_tasks_needing_subtitles()
    print(f"\n📊 待处理字幕任务: {len(tasks)} 个")
    
    if len(tasks) == 0:
        print("\n✅ 没有待处理的字幕任务")
        print("\n提示: 需要满足以下条件的任务:")
        print("  1. status = 'archived' (已归档)")
        print("  2. tmdb_id 不为空 (已刮削)")
        print("  3. sub_status 为 'pending', 'missing' 或 'failed'")
        return
    
    # 4. 显示前 5 个任务
    print("\n前 5 个任务:")
    for i, task in enumerate(tasks[:5], 1):
        print(f"\n  [{i}] ID: {task['id']}")
        print(f"      文件: {task['file_name']}")
        print(f"      类型: {task['type']}")
        print(f"      TMDB ID: {task['tmdb_id']}")
        print(f"      IMDB ID: {task.get('imdb_id', 'N/A')}")
        print(f"      目标路径: {task.get('target_path', 'N/A')}")
        print(f"      字幕状态: {task.get('sub_status', 'N/A')}")
    
    # 5. 询问是否执行测试
    print("\n" + "=" * 60)
    choice = input("是否对第一个任务执行字幕下载测试? (y/n): ").strip().lower()
    
    if choice != 'y':
        print("❌ 测试已取消")
        return
    
    # 6. 执行字幕下载
    task = tasks[0]
    print(f"\n🚀 开始下载字幕...")
    print(f"   任务 ID: {task['id']}")
    print(f"   文件路径: {task['path']}")
    
    # 初始化字幕引擎
    subtitle_engine = SubtitleEngine(api_key=api_key, user_agent=user_agent)
    
    try:
        result = await subtitle_engine.download_subtitle_for_task(
            db_manager=db,
            file_path=task['path'],
            tmdb_id=task['tmdb_id'],
            media_type=task['type'],
            imdb_id=task.get('imdb_id'),
            target_path=task.get('target_path')
        )
        
        print(f"\n✅ 下载结果: {result}")
        
        # 7. 验证数据库更新
        task_id = task['id']
        conn = db.db_lock.__enter__()
        import sqlite3
        conn = sqlite3.connect(db.db_path)
        cursor = conn.execute(
            "SELECT sub_status, last_sub_check FROM tasks WHERE id = ?",
            (task_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row:
            print(f"\n📊 数据库状态:")
            print(f"   sub_status: {row[0]}")
            print(f"   last_sub_check: {row[1]}")
        
        # 8. 检查字幕文件
        target_path = task.get('target_path') or task['path']
        from pathlib import Path
        target_dir = Path(target_path).parent
        video_stem = Path(target_path).stem
        
        print(f"\n📁 检查字幕文件:")
        print(f"   目录: {target_dir}")
        
        subtitle_files = []
        if target_dir.exists():
            for f in target_dir.iterdir():
                if f.is_file() and f.suffix.lower() in ['.srt', '.ass']:
                    if f.name.lower().startswith(video_stem.lower()):
                        subtitle_files.append(f.name)
        
        if subtitle_files:
            print(f"   ✅ 找到 {len(subtitle_files)} 个字幕文件:")
            for sf in subtitle_files:
                print(f"      - {sf}")
        else:
            print(f"   ⚠️ 未找到字幕文件")
        
    except Exception as e:
        print(f"\n❌ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_subtitle_download())
