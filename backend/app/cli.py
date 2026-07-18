"""
CLI 工具 - 离线管理入口

职责：
- 提供无需 Web 界面的管理员维护能力。
- 直接读写 `data/auth.json`，用于初始化账号、查看管理员信息和重置密码。
- 复用 `CryptoManager` 的密码哈希能力，避免 CLI 与 Web 鉴权逻辑分叉。

适用场景：
- 忘记管理员密码，需要在宿主机或 Docker 容器内重置。
- 首次部署时希望通过脚本初始化管理员账号。
- 自动化运维脚本需要读取当前管理员基础信息。

安全边界：
- 密码不会明文落盘，只保存 Bcrypt 哈希。
- 本模块只处理管理员账号文件，不接触媒体库、任务表或配置仓储。
"""
import sys
import json
import os
from pathlib import Path

import click

from app.infra.security import get_crypto_manager


@click.group()
def cli():
    """Neon Crate CLI 工具"""
    pass


@cli.command()
@click.option('--username', default='admin', help='用户名 (默认: admin)')
@click.option('--password', default=None, help='新密码 (不指定则交互输入)')
def reset_password(username, password):
    """
    重置管理员密码
    
    使用方式：
    1. 交互式：python -m app.cli reset-password
    2. 指定密码：python -m app.cli reset-password --password newpass123
    3. Docker 内：docker exec -it neon-crate python -m app.cli reset-password
    
    安全机制：
    - 密码长度至少 6 个字符
    - 使用 Bcrypt 哈希存储，不明文保存
    - 直接修改 data/auth.json 文件
    """
    crypto = get_crypto_manager()
    
    # 检查系统是否已初始化
    if not crypto.is_initialized():
        click.echo("❌ 系统未初始化，请先通过 Web 界面初始化")
        sys.exit(1)
    
    # 如果没有指定密码，交互式输入
    if password is None:
        password = click.prompt('请输入新密码', hide_input=True, confirmation_prompt=True)
    
    if not password or len(password) < 6:
        click.echo("❌ 密码长度至少 6 个字符")
        sys.exit(1)
    
    try:
        # 生成密码哈希
        password_hash = crypto.get_password_hash(password)
        
        # 读取现有的 auth.json
        auth_path = crypto.auth_path
        with open(auth_path, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        
        # 更新密码哈希
        auth_data['password_hash'] = password_hash
        
        # 保存回文件
        with open(auth_path, 'w', encoding='utf-8') as f:
            json.dump(auth_data, f, indent=4, ensure_ascii=False)
        
        click.echo(f"✅ 密码已重置: {username}")
        click.echo(f"📝 请使用新密码登录: http://localhost:3000")
        
    except Exception as e:
        click.echo(f"❌ 重置失败: {str(e)}")
        sys.exit(1)


@cli.command()
def show_admin():
    """显示管理员信息"""
    crypto = get_crypto_manager()
    
    if not crypto.is_initialized():
        click.echo("❌ 系统未初始化")
        sys.exit(1)
    
    try:
        auth_path = crypto.auth_path
        with open(auth_path, 'r', encoding='utf-8') as f:
            auth_data = json.load(f)
        
        click.echo("📋 管理员信息:")
        click.echo(f"  用户名: {auth_data.get('username', 'N/A')}")
        click.echo(f"  创建时间: {auth_data.get('created_at', 'N/A')}")
        
    except Exception as e:
        click.echo(f"❌ 读取失败: {str(e)}")
        sys.exit(1)


@cli.command()
def init_admin():
    """初始化管理员账号 (CLI 模式)"""
    crypto = get_crypto_manager()
    
    if crypto.is_initialized():
        click.echo("❌ 系统已初始化，无需重复初始化")
        sys.exit(1)
    
    try:
        username = click.prompt('请输入用户名', default='admin')
        password = click.prompt('请输入密码', hide_input=True, confirmation_prompt=True)
        
        if not password or len(password) < 6:
            click.echo("❌ 密码长度至少 6 个字符")
            sys.exit(1)
        
        success = crypto.init_admin(username, password)
        
        if success:
            click.echo(f"✅ 管理员账号已创建")
            click.echo(f"  用户名: {username}")
            click.echo(f"📝 请访问 http://localhost:3000 登录")
        else:
            click.echo("❌ 初始化失败")
            sys.exit(1)
            
    except Exception as e:
        click.echo(f"❌ 初始化失败: {str(e)}")
        sys.exit(1)


if __name__ == '__main__':
    cli()
