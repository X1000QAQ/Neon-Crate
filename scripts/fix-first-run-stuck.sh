#!/bin/bash
# =============================================================================
# Neon Crate v1.0.0 — 首次启动卡死修复脚本
# 使用方案 B：架构级重构（推荐）
# =============================================================================

set -e  # 任何命令失败则退出

echo "🚀 Neon Crate 首次启动修复流程"
echo "=================================="
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 1 步：验证前端配置
# ═════════════════════════════════════════════════════════════════════════

echo "📋 [第 1/6 步] 验证前端配置..."

if ! grep -q "trailingSlash: true" frontend/next.config.js; then
  echo "❌ 错误：next.config.js 中未设置 trailingSlash: true"
  exit 1
fi

echo "✅ 前端配置正确"
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 2 步：清理旧构建
# ═════════════════════════════════════════════════════════════════════════

echo "🧹 [第 2/6 步] 清理旧构建..."

rm -rf frontend/out frontend/.next backend/static/*

echo "✅ 旧构建已清理"
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 3 步：构建前端（AIO 模式）
# ═════════════════════════════════════════════════════════════════════════

echo "🔨 [第 3/6 步] 构建前端（AIO 模式）..."

cd frontend

# 关键：设置环境变量启用静态导出模式
export NEXT_PUBLIC_BUILD_MODE=aio

echo "  📦 安装依赖..."
npm install > /dev/null 2>&1

echo "  🏗️ 构建静态导出..."
npm run build

cd ..

echo "✅ 前端构建完成"
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 4 步：验证前端构建结果
# ═════════════════════════════════════════════════════════════════════════

echo "🔍 [第 4/6 步] 验证前端构建结构..."

# 检查关键文件
declare -a files_to_check=(
  "frontend/out/index.html"
  "frontend/out/auth/login/index.html"
  "frontend/out/auth/login/index.txt"
  "frontend/out/setup/index.html"
  "frontend/out/setup/index.txt"
)

for file in "${files_to_check[@]}"; do
  if [ ! -f "$file" ]; then
    echo "❌ 缺失关键文件: $file"
    echo "💡 提示：检查 NEXT_PUBLIC_BUILD_MODE 是否正确设置"
    exit 1
  fi
  echo "  ✅ $file"
done

echo "✅ 所有关键文件验证通过"
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 5 步：复制前端产物到后端
# ═════════════════════════════════════════════════════════════════════════

echo "📋 [第 5/6 步] 复制前端产物到后端..."

cp -r frontend/out/* backend/static/

echo "  📂 验证复制结果..."
if [ ! -f backend/static/auth/login/index.html ]; then
  echo "❌ 复制失败"
  exit 1
fi

echo "✅ 前端产物已复制"
echo ""

# ═════════════════════════════════════════════════════════════════════════
# 第 6 步：提交代码到 GitHub
# ═════════════════════════════════════════════════════════════════════════

echo "💾 [第 6/6 步] 提交代码到 GitHub..."

git add -A
git commit -m "fix: rebuild frontend with correct AIO mode configuration

- Set NEXT_PUBLIC_BUILD_MODE=aio during build process
- Generate export mode with trailingSlash: true
- Create auth/login/index.html directory structure
- Create setup/index.html directory structure
- Generate RSC contract files (index.txt)

This fixes the 'stuck on initialization' issue by ensuring:
1. Next.js generates auth/login/index.html (not auth/login.html)
2. FastAPI SPA fallback can correctly serve index.html for subroutes
3. RSC contract files exist for client-side navigation
4. No 404 errors when accessing /auth/login/ directly

Ready for Docker build and Unraid deployment." || echo "⚠️ 没有新的更改需要提交"

if git push origin master 2>/dev/null; then
  echo "✅ 代码已推送到 GitHub"
else
  echo "⚠️ GitHub 推送失败（网络问题），但本地代码已准备好"
fi

echo ""
echo "=================================="
echo "✅ 修复完成！"
echo "=================================="
echo ""
echo "📌 后续步骤："
echo ""
echo "1️⃣  在 Windows PowerShell 中构建 Docker 镜像："
echo "    cd C:\\path\\to\\Neon-Crate"
echo "    docker build -t x1000qaq/neon-crate:v1.0.0 ."
echo "    docker push x1000qaq/neon-crate:v1.0.0"
echo ""
echo "2️⃣  在 Unraid 中更新容器："
echo "    docker pull x1000qaq/neon-crate:v1.0.0"
echo "    docker-compose up -d"
echo ""
echo "3️⃣  验证修复成功："
echo "    访问 http://192.168.0.98:8000/"
echo "    应该看到登录界面而不是卡死的初始化画面"
echo ""
echo "💡 快速验证（无需重建 Docker）："
echo "    直接访问 http://192.168.0.98:8000/"
echo "    而不是 /auth/login/"
echo ""
