# ============================================================================
# Neon Crate — AIO 工业级多阶段构建 Dockerfile
# 架构哲学：单容器 · 单端口（8000）· 零跨域 · NAS 友好
# ============================================================================

# ============================================================================
# 🚀 第一阶段：前端构建（Node.js 20）
# ============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 1. 拷贝前端依赖配置
COPY frontend/package*.json ./

# 2. 安装依赖（ci 模式：严格锁定版本，保证构建可复现）
RUN npm ci

# 3. 拷贝前端源码
COPY frontend ./

# 4. 构建静态导出产物（next.config.js 中 output: 'export' 已启用）
#    产物输出至 /app/frontend/out/
RUN npm run build

# ============================================================================
# 🚀 第二阶段：后端运行环境（Python 3.12）
# ============================================================================
FROM python:3.12-slim

WORKDIR /app

# 设置环境变量，确保 Python 输出不被缓冲
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 安装系统级依赖（gcc 用于部分 Python 扩展编译，curl 用于健康检查）
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 1. 拷贝后端依赖配置
COPY backend/requirements.txt .

# 2. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 3. 拷贝后端业务代码
COPY backend/app ./app

# 🚨 架构级合并：将第一阶段的 Next.js 静态产物注入后端 static/ 目录
#    FastAPI main.py 通过 StaticFiles 挂载此目录，实现 AIO 单端口托管
COPY --from=frontend-builder /app/frontend/out ./static

# 建立数据持久化防线
RUN mkdir -p /app/data/logs && \
    mkdir -p /app/data/posters

# 暴露 AIO 单端口
EXPOSE 8000

# 健康检查：每 30s 检查一次，3 次失败判定为不健康
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 🚀 启动 AIO 引擎
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
