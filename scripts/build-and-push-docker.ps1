# =============================================================================
# Neon Crate v1.0.0 — Docker 镜像构建与推送脚本（Windows PowerShell）
# =============================================================================

param(
    [switch]$SkipDockerBuild = $false,
    [switch]$SkipPush = $false
)

Write-Host "🚀 Neon Crate Docker 构建与推送流程" -ForegroundColor Cyan
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

# ═════════════════════════════════════════════════════════════════════════
# 第 1 步：验证前端文件已准备好
# ═════════════════════════════════════════════════════════════════════════

Write-Host "🔍 [第 1/4 步] 验证前端文件..." -ForegroundColor Yellow

$filesToCheck = @(
    "frontend\out\index.html",
    "frontend\out\auth\login\index.html",
    "frontend\out\setup\index.html",
    "backend\static\auth\login\index.html",
    "backend\static\setup\index.html"
)

foreach ($file in $filesToCheck) {
    if (-Not (Test-Path $file)) {
        Write-Host "❌ 缺失文件: $file" -ForegroundColor Red
        Write-Host "💡 请先在 WSL2/Linux 中运行: bash scripts/fix-first-run-stuck.sh" -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  ✅ $file" -ForegroundColor Green
}

Write-Host "✅ 所有前端文件已准备好" -ForegroundColor Green
Write-Host ""

# ═════════════════════════════════════════════════════════════════════════
# 第 2 步：Docker 登录
# ═════════════════════════════════════════════════════════════════════════

Write-Host "🔐 [第 2/4 步] Docker 登录..." -ForegroundColor Yellow

if (-Not $SkipDockerBuild) {
    Write-Host "请输入 Docker Hub 凭证..." -ForegroundColor Cyan
    docker login
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Docker 登录失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Docker 登录成功" -ForegroundColor Green
}

Write-Host ""

# ═════════════════════════════════════════════════════════════════════════
# 第 3 步：构建 Docker 镜像
# ═════════════════════════════════════════════════════════════════════════

if (-Not $SkipDockerBuild) {
    Write-Host "🐳 [第 3/4 步] 构建 Docker 镜像..." -ForegroundColor Yellow
    
    Write-Host "  🔨 docker build -t x1000qaq/neon-crate:v1.0.0 ." -ForegroundColor Cyan
    docker build -t x1000qaq/neon-crate:v1.0.0 .
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Docker 构建失败" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "  🏷️  标记为 latest..." -ForegroundColor Cyan
    docker tag x1000qaq/neon-crate:v1.0.0 x1000qaq/neon-crate:latest
    
    Write-Host "✅ Docker 镜像构建完成" -ForegroundColor Green
} else {
    Write-Host "⏭️  跳过 Docker 构建 (-SkipDockerBuild)" -ForegroundColor Yellow
}

Write-Host ""

# ═════════════════════════════════════════════════════════════════════════
# 第 4 步：推送到 Docker Hub
# ═════════════════════════════════════════════════════════════════════════

if (-Not $SkipPush) {
    Write-Host "📤 [第 4/4 步] 推送到 Docker Hub..." -ForegroundColor Yellow
    
    Write-Host "  📦 推送 v1.0.0..." -ForegroundColor Cyan
    docker push x1000qaq/neon-crate:v1.0.0
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ 推送 v1.0.0 失败" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "  📦 推送 latest..." -ForegroundColor Cyan
    docker push x1000qaq/neon-crate:latest
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ 推送 latest 失败" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "✅ Docker 镜像推送完成" -ForegroundColor Green
} else {
    Write-Host "⏭️  跳过 Docker 推送 (-SkipPush)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "===================================" -ForegroundColor Cyan
Write-Host "✅ 所有步骤完成！" -ForegroundColor Green
Write-Host "===================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "📌 后续步骤：" -ForegroundColor Cyan
Write-Host ""
Write-Host "在 Unraid 中更新容器：" -ForegroundColor Yellow
Write-Host "  docker pull x1000qaq/neon-crate:v1.0.0" -ForegroundColor Cyan
Write-Host "  docker-compose down" -ForegroundColor Cyan
Write-Host "  docker-compose up -d" -ForegroundColor Cyan
Write-Host ""
Write-Host "验证修复成功：" -ForegroundColor Yellow
Write-Host "  访问 http://192.168.0.98:8000/" -ForegroundColor Cyan
Write-Host "  应该看到登录界面（不再卡死）" -ForegroundColor Cyan
Write-Host ""
