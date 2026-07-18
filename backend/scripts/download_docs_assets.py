"""
API 文档静态资源下载脚本 (增强版)

功能：
- 增加 User-Agent 伪装，规避 CDN 的简单机器人拦截
- 自动处理目录创建
- 支持离线环境的资源准备

使用方法：
    cd backend
    python scripts/download_docs_assets.py
"""
import asyncio
import httpx
from pathlib import Path

# 静态资源目录
DOCS_DIR = Path(__file__).parent.parent / "static" / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Swagger UI 资源列表 (版本 5.9.0)
# 我们提供多个源作为备选
RESOURCES = {
    "swagger-ui-bundle.js": [
        "https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"
    ],
    "swagger-ui.css": [
        "https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui.css"
    ],
    "swagger-ui-standalone-preset.js": [
        "https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js",
        "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"
    ],
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

async def download_file(filename, urls, client):
    """尝试从多个 URL 下载同一个文件"""
    for url in urls:
        print(f"📥 正在尝试下载 {filename} 来自 {url.split('/')[2]}...")
        try:
            resp = await client.get(url, headers=HEADERS, follow_redirects=True)
            if resp.status_code == 200:
                file_path = DOCS_DIR / filename
                file_path.write_bytes(resp.content)
                size_kb = len(resp.content) / 1024
                print(f"   ✅ 成功! ({size_kb:.1f} KB)")
                return True
            else:
                print(f"   ⚠️  状态码错误: {resp.status_code}")
        except Exception as e:
            print(f"   ❌ 网络请求失败: {str(e)}")
    return False

async def download_assets():
    """下载所有静态资源"""
    print("=" * 60)
    print("📦 Neon Crate API 文档离线资源同步器")
    print("=" * 60)
    print(f"\n目标本地目录: {DOCS_DIR}\n")
    
    # 禁用代理（如果环境中有干扰，可以尝试设为 None）
    async with httpx.AsyncClient(timeout=60.0, proxies=None) as client:
        tasks = [download_file(fname, urls, client) for fname, urls in RESOURCES.items()]
        results = await asyncio.gather(*tasks)
    
    print("\n" + "=" * 60)
    if all(results):
        print("🎉 所有离线资源已就绪！系统现在可以完全脱离互联网运行。")
    else:
        print("🚨 部分资源下载失败。")
        print("💡 建议：如果脚本持续失败，请根据下方链接通过浏览器手动下载：")
        for fname, urls in RESOURCES.items():
            print(f"  - {fname}: {urls[0]}")
    print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(download_assets())
    except KeyboardInterrupt:
        print("\n操作已取消。")