# Neon Crate — AIO 全栈部署指南 V1.1
**文档版本**：V1.1 正式版  
**编制日期**：2026-03-12  
**项目代号**：Neon Crate  
**文档编号**：ARCH-OPS-006  
**维护者**：Neon Crate 架构 & DevOps 团队  
**深度索引来源**：`docs/03_后端模块手册/*` + `docs/04_前端模块手册/*`
---

## 文档概述

本指南详细记录 Neon Crate 的 **AIO（All-In-One）部署模式**，以后端模块手册（`03_后端模块手册`）和前端模块手册（`04_前端模块手册`）为深度索引，覆盖从源码构建、环境配置、本地裸机启动到 Docker Compose 容器编排的完整部署链路。
**V1.1 相较 V1.0 的主要变化**：
| 变更项 | 说明 |
|--------|------|
| 深度引用模块手册 | 所有配置项、启动日志、环境变量均与 `infra/config.md`、`main.md`、`database.md` 对齐 |
| 新增「环境变量全参考表」 | 覆盖 Settings 所有字段，明确生产必改项 |
| 新增「首次启动初始化流程」 | 详述管理员账号初始化、DB 自动迁移、AI 规则注入三大步骤 |
| 新增「数据持久化与备份策略」 | 覆盖 `data/` 目录所有关键文件的备份建议 |
| 扩充「故障排查」 | 与 V1.1 架构修复（双表删除、季号回写、stats 缓存）对齐 |
| Ollama 本地 LLM 部署说明 | 补充 AIO 环境下 Ollama 内存预留和 Docker 网络配置 |
**核心优势**：
- 单端口访问（8000），零跨域
- 单 Python 进程同时提供前后端服务
- 内存占用约 300MB（vs 分离模式 500MB+）
- Docker 镜像无需 Node.js 运行时
> **【V1.1 Ollama 说明】**  
> 本版本支持本地大模型能力（Ollama 引擎）。在纯内网/无云端 API 的部署场景下，请为宿主机预留充足可用内存供 Ollama 使用（7B 模型建议 ≥8GB，72B 模型建议 ≥64GB），避免容器或其他服务将物理内存耗尽，导致大模型加载 OOM 或被系统强制回收。
---

## 目录

1. [AIO 架构原理解析](#一aio-架构原理解析)
2. [部署前置条件](#二部署前置条件)
3. [环境变量配置参考](#三环境变量配置参考)
4. [前端静态化构建](#四前端静态化构建)
5. [后端 SPA 路由接管机制](#五后端-spa-路由接管机制)
6. [首次启动初始化流程](#六首次启动初始化流程)
7. [生产环境启动方案](#七生产环境启动方案)
8. [Docker Compose 容器编排](#八docker-compose-容器编排)
9. [Ollama 本地 LLM 集成](#九ollama-本地-llm-集成)
10. [数据持久化与备份策略](#十数据持久化与备份策略)
11. [故障排查手册](#十一故障排查手册)
12. [部署检查清单](#十二部署检查清单)
13. [模式对比与选型建议](#十三模式对比与选型建议)
---

## 一、AIO 架构原理解析

### 1.1 核心概念

**AIO（All-In-One）模式**的核心思想：将 Next.js 应用通过 `output: 'export'` 编译为纯静态 HTML/CSS/JS 产物，由 FastAPI 后端通过 `StaticFiles` 中间件统一托管，生产环境只需一个 Python 进程、一个端口即可提供完整的前后端服务。
这一「前端 `output: 'export'` + FastAPI `StaticFiles` 静态挂载」的组合是 AIO 模式的灵魂所在，V1.1 完全沿用并在此基础上扩展了模块手册的对齐深度。

### 1.2 架构对比

#### 传统分离模式（开发环境）
```
浏览器
  └─► Next.js Dev Server :3000   # Node.js 进程
        └─► rewrites 代理
              └─► FastAPI :8000  # Python 进程
                    └─► SQLite / 外部 API
```
**特点**：前后端独立进程，需配置 CORS 或 rewrites 代理，支持热重载，适合本地开发。
#### AIO 模式（生产环境）
```
浏览器
  └─► FastAPI :8000              # 单一 Python 进程
        ├─► /api/v1/*  →  API 路由层（JWT 保护）
        ├─► /health    →  健康检查（豁免）
        └─► /*         →  static/ 前端静态资源
                             └─► SPA 404 回退 → index.html
```
**特点**：单进程、无 CORS、无 Node.js 运行时、部署极简。

### 1.3 路由优先级（来自 `main.md`）

根据后端模块手册 `main.md` 的路由注册顺序，优先级由高到低为：
```
优先级 1：/api/v1/auth/*       鉴权路由（无 JWT 豁免）
优先级 2：/api/v1/public/*     公共路由（有 JWT，图片代理）
优先级 3：/api/v1/*            业务路由（全局 JWT 依赖注入）
优先级 4：/health              健康检查（豁免，内联 Handler）
优先级 5：/*                   前端静态文件（最低，StaticFiles 兜底）
```
确保 API 路由永远先于静态文件被匹配，SPA 404 回退处理器仅对非 `/api` 前缀的未知路径生效。

### 1.4 适用场景

| 场景 | 推荐模式 |
|------|----------|
| 生产部署（家庭服务器/NAS/VPS）| **AIO 模式** |
| Docker 单容器/单节点部署 | **AIO 模式** |
| 资源受限（树莓派、低配 VPS）| **AIO 模式** |
| 本地开发调试、热重载需求 | 分离模式 |
| 前端样式频繁迭代 | 分离模式 |
---

## 二、部署前置条件

### 2.1 系统要求

| 项目 | 最低要求 | 推荐配置 |
|------|----------|----------|
| 操作系统 | Linux / macOS / Windows | Linux（Debian/Ubuntu）|
| Python | 3.10+ | 3.12 |
| Node.js | 18+（仅构建阶段需要）| 20 LTS |
| 内存 | 512MB（不含 Ollama）| 2GB+ |
| 磁盘 | 10GB（系统 + 数据）| 视媒体库规模而定 |
| Docker | 24.0+（容器化部署）| 最新稳定版 |
| Docker Compose | V2（`docker compose` 命令）| 最新稳定版 |

### 2.2 网络要求

| 外部服务 | 用途 | 是否必须 |
|----------|------|----------|
| TMDB API | 电影/剧集元数据刮削 | 是（核心功能）|
| OpenSubtitles API | 字幕下载 | 否（字幕功能需要）|
| Radarr / Sonarr | AI 指令下载触发 | 否（AI 下载功能需要）|
| LLM API（云端）| DeepSeek / Together 等 | 否（可用 Ollama 替代）|
| Ollama（本地）| 本地大模型推理 | 否（可用云端 API 替代）|

### 2.3 源码获取

```bash
git clone https://github.com/your-org/neon-crate.git
cd neon-crate
```
项目顶层结构：
```
Neon-Crate/
├── backend/          # FastAPI 后端
├── frontend/         # Next.js 前端
├── docs/             # 项目文档
└── docker-compose.yml
```
---

## 三、环境变量配置参考

> 深度索引：`docs/03_后端模块手册/01_infra/config.md`
后端配置基于 **pydantic-settings**，支持通过 `.env` 文件或系统环境变量覆盖。配置类 `Settings(BaseSettings)` 位于 `backend/app/infra/config/__init__.py`，带 `lru_cache` 缓存，进程生命周期内只解析一次。

### 3.1 创建 .env 文件

```bash
cp backend/.env.example backend/.env
```

### 3.2 完整环境变量参考表

以下字段均来自 `infra/config.md` 的 `Settings` 类定义：
| 变量名 | 默认值 | 生产必改 | 说明 |
|--------|--------|----------|------|
| `APP_NAME` | `"Neon Crate"` | 否 | 应用名称标识 |
| `APP_VERSION` | `"1.0.0"` | 否 | 应用版本号 |
| `HOST` | `"0.0.0.0"` | 否 | 监听地址，`0.0.0.0` 允许外部访问 |
| `PORT` | `8000` | 否 | 监听端口 |
| `DEBUG` | `False` | 否 | 调试模式，**生产必须为 False** |
| `LOG_LEVEL` | `"INFO"` | 否 | 日志级别：`DEBUG/INFO/WARNING/ERROR` |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | 否 | AIO 模式下无需修改（同端口无跨域）|
| `DOCKER_STORAGE_PATH` | `"/storage"` | **是** | Docker 媒体挂载点，须与 volumes 一致 |
| `DB_PATH` | `"data/media_database.db"` | 否 | SQLite 数据库路径（相对于 backend/ 目录）|
| `CONFIG_PATH` | `"data/config.json"` | 否 | 应用配置文件路径（含加密 API Key）|
| `JWT_SECRET_KEY` | `"your-secret-key..."` | **是** | JWT 签名密钥，**生产环境必须替换为强随机值** |
| `JWT_ALGORITHM` | `"HS256"` | 否 | JWT 算法 |
| `JWT_EXPIRE_DAYS` | `7` | 否 | Token 过期天数 |
| `API_V1_PREFIX` | `"/api/v1"` | 否 | API 路由前缀 |

### 3.3 生产环境 .env 示例

```env
# === 生产必改项 ===
JWT_SECRET_KEY=请替换为64位以上随机字符串
DOCKER_STORAGE_PATH=/mnt/media
# === 可选调整项 ===
APP_NAME=Neon Crate
HOST=0.0.0.0
PORT=8000
DEBUG=False
LOG_LEVEL=INFO
JWT_EXPIRE_DAYS=7
```
> **安全提示**：`JWT_SECRET_KEY` 默认值仅供开发，生产环境务必替换。推荐生成方式：
> ```bash
> python3 -c "import secrets; print(secrets.token_hex(64))"
> ```
> **注意**：`lru_cache` 机制意味着修改 `.env` 后必须**重启服务**才能生效，热更新无效。
---

## 四、前端静态化构建

> 深度索引：`docs/04_前端模块手册/01_app/layout.md`

### 4.1 Next.js 导出配置

**配置文件**：`frontend/next.config.js`
AIO 模式的关键配置点（与前端架构白皮书 V1.1 对齐）：
```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'export',        // [关键] 启用纯静态导出，不生成 Node.js Server
  images: {
    unoptimized: true      // [必需] 静态导出不支持 Next.js 图片优化服务
  },
  trailingSlash: true,     // [推荐] 为路由生成 /dashboard/index.html 格式
  // [重要] 不得保留 rewrites 配置，AIO 模式下会导致构建失败
}
module.exports = nextConfig
```
**配置禁忌**：
| 禁止项 | 原因 |
|--------|------|
| 保留 `rewrites` | 静态导出不支持运行时路由代理，构建报错 |
| 保留 `serverActions` | 需要 Node.js 运行时，与静态导出不兼容 |
| 使用 `getServerSideProps` | SSR 函数无法在纯静态模式下运行 |

### 4.2 安装依赖与构建

```bash
# 进入前端目录
cd frontend
# 安装依赖（首次或 package.json 变更后执行）
npm install
# 执行生产构建
npm run build
```
**构建成功输出**：
```
> neon-crate-frontend@1.1.0 build
> next build
   Creating an optimized production build ...
 ✓ Compiled successfully
 ✓ Linting and checking validity of types
 ✓ Collecting page data
 ✓ Generating static pages (6/6)
 ✓ Finalizing page optimization
Export Output: out/
```
**验证构建产物**：
```bash
ls out/
# 预期包含：index.html  auth/  _next/  public/
```

### 4.3 静态产物转移

将构建产物 `out/` 目录移动至后端，重命名为 `static/`，FastAPI 的 `StaticFiles` 从此目录提供前端服务。
**Linux / macOS**：
```bash
# 清除旧产物（如存在）
rm -rf ../backend/static
# 转移并重命名
mv out ../backend/static
# 返回项目根目录
cd ..
# 验证
ls -lh backend/static/index.html
```
**Windows PowerShell**：
```powershell
# 清除旧产物
Remove-Item -Recurse -Force ..\backend\static -ErrorAction SilentlyContinue
# 转移并重命名
Move-Item out ..\backend\static
cd ..
# 验证
Test-Path backend\static\index.html
```
**一键自动化脚本**（推荐写入 `Makefile` 或 `build.sh`）：
```bash
#!/bin/bash
set -e
echo "[1/3] 安装前端依赖..."
cd frontend && npm install
echo "[2/3] 构建前端静态产物..."
npm run build
echo "[3/3] 转移产物到后端..."
rm -rf ../backend/static
mv out ../backend/static
echo "✓ 前端构建完成: backend/static/index.html"
cd ..
```

### 4.4 常见构建错误

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| `Page missing generateStaticParams()` | 动态路由未提供静态参数 | 添加 `generateStaticParams()` 函数 |
| `Image Optimization not compatible with export` | 使用了 `<Image>` 但未禁用优化 | `next.config.js` 添加 `images: { unoptimized: true }` |
| `rewrites is not supported in static export` | 配置了 `rewrites` | 删除 `next.config.js` 中的 `rewrites` 函数 |
| `useSearchParams() should be wrapped in a Suspense` | App Router 约束 | 在使用 `useSearchParams` 的组件外包 `<Suspense>` |
---

## 五、后端 SPA 路由接管机制

> 深度索引：`docs/03_后端模块手册/main.md`

### 5.1 静态目录挂载

**核心代码**（`backend/app/main.py`）：
```python
from fastapi.staticfiles import StaticFiles
import os
_frontend_static = "static"
if os.path.isdir(_frontend_static):
    app.mount("/", StaticFiles(directory=_frontend_static, html=True), name="frontend")
    print(f"[OK] 前端静态文件已挂载: {_frontend_static} -> /")
else:
    print(f"[INFO] 未找到前端静态目录 {_frontend_static}，AIO 模式未启用")
```
**参数说明**：
- `html=True`：启用 HTML 文件自动索引，访问 `/auth/login/` 自动查找 `auth/login/index.html`
- 挂载路径 `/`：优先级最低，只有所有 API 路由均未命中时才进入静态文件查找
- 目录检测：启动时若 `backend/static/` 不存在，系统以 API-only 模式运行，不报错

### 5.2 媒体资源挂载

```python
# 来自 main.md —— 静态资源挂载逻辑
if os.path.isdir(settings.DOCKER_STORAGE_PATH):
    app.mount("/api/v1/assets",
              StaticFiles(directory=settings.DOCKER_STORAGE_PATH),
              name="assets")
    print(f"[OK] 静态资源已挂载: {settings.DOCKER_STORAGE_PATH} -> /api/v1/assets")
else:
    # 回退到本地 data/posters/
    fallback = "data/posters"
    if os.path.isdir(fallback):
        app.mount("/api/v1/assets", StaticFiles(directory=fallback), name="assets")
```
**访问示例**：
```
宿主机路径: /mnt/media/movies/Avatar (2009)/poster.jpg
容器内路径: /storage/movies/Avatar (2009)/poster.jpg
HTTP 访问:  http://your-host:8000/api/v1/assets/movies/Avatar (2009)/poster.jpg
```
> 前端所有本地图片必须通过 `/api/v1/public/image?path=...` 安全代理访问，不得直接拼接物理路径。参见 `03_后端模块手册/01_infra/security.md` 的路径安全防护章节。

### 5.3 SPA 404 回退处理器

**核心问题**：用户在浏览器地址栏直接访问 `/auth/login`、刷新 `/dashboard` 等前端路由时，FastAPI 找不到对应路由，返回 404。
**解决方案**（`backend/app/main.py`）：
```python
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
@app.exception_handler(404)
async def spa_fallback_handler(request, exc):
    # API 请求返回标准 JSON 404，避免前端收到 HTML 解析报错
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    # 其他所有路径回退到 index.html，由前端 React Router 接管
    index_path = Path("static/index.html")
    if index_path.exists():
        return FileResponse("static/index.html")
    else:
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
```
**完整请求处理流程**：
```
用户访问 /dashboard
  ↓
FastAPI 路由匹配
  ├─► 命中 /api/v1/* → 正常处理 API 请求
  ├─► 命中静态文件  → 返回对应文件
  └─► 未命中 → 触发 404 异常
                  ↓
           spa_fallback_handler
                  ├─► 路径以 /api 开头 → JSON 404
                  └─► 其他路径 → FileResponse(static/index.html)
                                    ↓
                              浏览器加载 index.html
                                    ↓
                              React Router 接管
                                    ↓
                              渲染 /dashboard 页面组件
```
---

## 六、首次启动初始化流程

> 深度索引：`docs/03_后端模块手册/01_infra/database.md`、`docs/03_后端模块手册/01_infra/security.md`
首次启动时，系统自动完成三个初始化阶段，无需人工干预：

### 6.1 阶段一：数据库自动初始化

触发模块：`backend/app/infra/database/db_manager.py`
```
DatabaseManager 懒初始化
  ├─► PRAGMA journal_mode=WAL      开启 WAL 模式（提升并发读取）
  ├─► 自动建表
  │     ├─► tasks 表（媒体任务主表，path UNIQUE 防重入库）
  │     ├─► media_archive 表（归档记录表，独立自增 ID）
  │     └─► config 表（KV 配置存储）
  ├─► _migrate_plaintext_keys()   历史明文 API 密钥迁移为 Fernet 加密
  └─► _inject_ai_defaults()       注入 AI 人格 / 路由规则 / 归档规则 / 15条正则
```
**`tasks` 与 `media_archive` 双表说明**（来自 `database.md`）：
- `tasks.id` 与 `media_archive.id` 各自独立自增，同一文件在两张表中的 `id` 不同
- 删除操作必须按 `path` 匹配，不得用 `id` 对删（V1.1 已修复历史 Bug）
- `media_archive` 记录归档完成后的完整元数据，含 `season`、`episode`、`sub_status`

### 6.2 阶段二：安全模块初始化

触发模块：`backend/app/infra/security/crypto.py`（神盾计划 Project Aegis）
```
CryptoManager 懒初始化
  ├─► 检查 data/secret.key 是否存在
  │     ├─► 存在 → 加载 Fernet 主密钥
  │     └─► 不存在 → 自动生成新密钥，写入文件，权限设为 0o600
  └─► 该密钥同时用于：
        ├─► Fernet 加密：6 个敏感 API Key 字段
        └─► JWT 签名：Bearer Token（7天过期，HS256）
```
**敏感键列表**（自动加密存储，读取时自动解密）：
```python
SENSITIVE_KEYS = [
    "tmdb_api_key",    # TMDB API 密钥
    "os_api_key",      # OpenSubtitles API 密钥
    "sonarr_api_key",  # Sonarr API 密钥
    "radarr_api_key",  # Radarr API 密钥
    "llm_cloud_key",   # 云端 LLM API 密钥
    "llm_local_key",   # 本地 LLM API 密钥
]
```

### 6.3 阶段三：管理员账号初始化（首次访问 WebUI）

触发接口：`POST /api/v1/auth/init`（来自 `02_api/auth.md`）
系统首次启动后，访问 `http://your-host:8000` 会被前端 `AuthGuard.tsx` 检测到未初始化状态，自动跳转到初始化页面。
**WebUI 操作步骤**：
1. 浏览器访问 `http://your-host:8000`
2. 系统检测 `GET /api/v1/auth/status` → `{ "initialized": false }`
3. 前端自动显示「创建管理员账号」表单
4. 填写用户名（≥3字符）和密码（≥6字符），点击确认
5. 后端调用 `CryptoManager.init_admin()`，bcrypt 哈希密码写入 `data/auth.json`
6. 自动颁发 JWT Token，前端存入 `localStorage.token`
7. 进入主界面 Dashboard
**约束**：`POST /api/v1/auth/init` 仅允许执行一次，重复调用返回 `HTTP 400`。

### 6.4 启动日志解读

正常启动时，终端应输出如下关键日志（来自 `main.md` 启动序列）：
```
============================================================
[START] Neon Crate v1.0.0 正在启动...
============================================================
[OK] 数据库初始化完成 (WAL 模式 + 原子写入)
[OK] AI 规则注入完成 (首次启动)
[OK] Docker 影音挂载点已就绪: /storage
[OK] 静态资源已挂载: /storage -> /api/v1/assets
[OK] 前端静态文件已挂载: static -> /         ← AIO 模式确认标志
[INFO] API 文档地址: http://0.0.0.0:8000/docs
============================================================
INFO:     Started server process [PID]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```
**关键标志判断**：
| 日志行 | 含义 |
|--------|------|
| `[OK] 前端静态文件已挂载: static -> /` | AIO 模式已启用，前端可访问 |
| `[INFO] 未找到前端静态目录 static` | 前端未构建，仅 API 可用 |
| `[OK] 静态资源已挂载: /storage -> /api/v1/assets` | 媒体海报可访问 |
| `[OK] AI 规则注入完成` | 首次启动，正则/AI 规则已写入数据库 |
---

## 七、生产环境启动方案

### 7.1 前置条件检查

```bash
# 检查前端产物
ls backend/static/index.html
# 检查后端依赖
cd backend
pip install -r requirements.txt
# 检查 .env 文件
cat .env | grep JWT_SECRET_KEY
```

### 7.2 方案 A：uvicorn 直接启动（最简单）

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```
**参数解析**：
| 参数 | 说明 |
|------|------|
| `python -m uvicorn` | 以模块方式运行，确保正确的 Python 路径 |
| `app.main:app` | 模块路径 `app.main` 中的 `app` FastAPI 实例 |
| `--host 0.0.0.0` | 监听所有网络接口（允许局域网访问）|
| `--port 8000` | 监听端口，与 `Settings.PORT` 对应 |

### 7.3 方案 B：uvicorn 多进程模式（推荐生产）

```bash
cd backend
python -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info \
  --access-log
```
**参数说明**：
| 参数 | 说明 |
|------|------|
| `--workers 4` | 启动 4 个工作进程，建议设为 CPU 核心数 |
| `--log-level info` | 日志级别，可选 `debug/info/warning/error` |
| `--access-log` | 输出每条 HTTP 访问日志 |
> **注意**：多进程模式下，后台 `asyncio` 巡逻任务（`cron_scanner_loop`）在每个 worker 中独立运行。若需避免重复触发，建议生产环境使用单进程 + 外部进程管理器（systemd/supervisor）。

### 7.4 方案 C：Gunicorn + UvicornWorker（最健壮）

```bash
pip install gunicorn
cd backend
gunicorn app.main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
```
**适用场景**：对稳定性要求高的生产环境，Gunicorn 提供更完善的 worker 生命周期管理和信号处理。

### 7.5 方案 D：systemd 服务（开机自启）

创建服务文件 `/etc/systemd/system/neon-crate.service`：
```ini
[Unit]
Description=Neon Crate AIO Media Management Service
After=network.target
[Service]
Type=exec
User=your-user
WorkingDirectory=/path/to/Neon-Crate/backend
EnvironmentFile=/path/to/Neon-Crate/backend/.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
```
**启用并启动**：
```bash
sudo systemctl daemon-reload
sudo systemctl enable neon-crate
sudo systemctl start neon-crate
# 查看状态
sudo systemctl status neon-crate
# 查看日志
sudo journalctl -u neon-crate -f
```

### 7.6 部署验证

```bash
# 步骤1：健康检查
curl http://localhost:8000/health
# 期望响应：{"status": "healthy", "service": "Neon Crate", ...}
# 步骤2：鉴权状态
curl http://localhost:8000/api/v1/auth/status
# 期望响应：{"initialized": false} 或 {"initialized": true}
# 步骤3：前端页面
curl -s http://localhost:8000 | grep -o '<title>.*</title>'
# 期望响应：包含 Neon Crate 的 HTML title
# 步骤4：SPA 回退验证
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/dashboard
# 期望响应：200（返回 index.html，而非 404）
# 步骤5：API 404 验证（确保 API 错误不返回 HTML）
curl http://localhost:8000/api/v1/nonexistent
# 期望响应：{"detail": "Not Found"}（JSON，非 HTML）
```
---

## 八、Docker Compose 容器编排

### 8.1 Dockerfile 说明

**后端 Dockerfile**（`backend/Dockerfile`）核心阶段：
```dockerfile
FROM python:3.12-slim
WORKDIR /app
# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 复制应用代码
COPY app/ ./app/
# 复制前端静态产物（构建时已放入 backend/static/）
COPY static/ ./static/
# 创建数据目录
RUN mkdir -p data/logs data/posters
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
> **关键**：`COPY static/ ./static/` 这一行要求在 `docker build` 前必须先完成前端构建并转移产物（参见第四章）。

### 8.2 docker-compose.yml

项目根目录的 `docker-compose.yml`（AIO 模式下仅需启动 backend 服务）：
```yaml
version: '3.8'
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: neon-crate-engine
    ports:
      - "8000:8000"
    volumes:
      # 数据持久化：数据库、配置、海报、日志
      - ./backend/data:/app/data
      # 媒体存储挂载（修改为实际路径）
      - /path/to/your/media:/storage
    environment:
      - APP_NAME=Neon Crate
      - HOST=0.0.0.0
      - PORT=8000
      - LOG_LEVEL=INFO
      - DOCKER_STORAGE_PATH=/storage
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-请替换为强随机密钥}
    restart: unless-stopped
    networks:
      - neon-crate-net
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
networks:
  neon-crate-net:
    driver: bridge
```

### 8.3 完整容器化部署流程

```bash
# 步骤1：构建前端静态产物
cd frontend
npm install && npm run build
mv out ../backend/static
cd ..
# 步骤2：配置环境变量
export JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))")
# 或写入 .env 文件
echo "JWT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(64))')" >> .env
# 步骤3：构建并启动容器
docker compose up -d --build
# 步骤4：查看启动日志
docker compose logs -f backend
# 步骤5：验证服务
curl http://localhost:8000/health
```

### 8.4 日常运维命令

```bash
# 查看运行状态
docker compose ps
# 查看实时日志
docker compose logs -f backend
# 重启服务
docker compose restart backend
# 停止服务
docker compose down
# 更新部署（重新构建前端后）
rm -rf backend/static
cd frontend && npm run build && mv out ../backend/static && cd ..
docker compose up -d --build backend
# 进入容器 Shell
docker compose exec backend bash
# 查看容器资源占用
docker stats neon-crate-engine
```

### 8.5 数据卷说明

| 宿主机路径 | 容器路径 | 说明 |
|------------|----------|------|
| `./backend/data` | `/app/data` | 数据库、配置、密钥、海报、日志 |
| `/path/to/your/media` | `/storage` | 媒体文件存储（须与 `DOCKER_STORAGE_PATH` 一致）|
> **重要**：`./backend/data` 目录包含 `secret.key`（Fernet 主密钥）和 `auth.json`（管理员账号），**必须持久化挂载，绝不能删除**，否则所有加密配置将无法解密，需重新初始化。
---

## 九、Ollama 本地 LLM 集成

### 9.1 架构说明

Neon Crate 的 AI Agent（`services/ai/llm_client.py`）兼容所有 OpenAI 格式 API，Ollama 通过其 OpenAI 兼容端点接入，无需任何代码改动。
```
AIAgent.process_message()
  └─► LLMClient.call_llm()
        └─► POST http://host.docker.internal:11434/v1/chat/completions
              └─► Ollama 本地推理引擎
                    └─► qwen2.5 / llama3 / deepseek 等模型
```

### 9.2 Ollama 安装与模型下载

```bash
# 安装 Ollama（Linux）
curl -fsSL https://ollama.com/install.sh | sh
# 下载推荐模型（选一）
ollama pull qwen2.5        # 7B，适合 8GB 内存
ollama pull qwen2.5:14b    # 14B，适合 16GB 内存
ollama pull deepseek-r1    # 7B，推理能力强
# 验证 Ollama 服务
curl http://localhost:11434/v1/models
```

### 9.3 内存预留建议

| 模型规模 | 宿主机最低可用内存 | 说明 |
|----------|--------------------|----- |
| 7B 量化版（Q4）| 6GB | 适合低配 NAS |
| 7B 全精度 | 8GB | 响应质量更好 |
| 14B 量化版（Q4）| 12GB | 推荐家庭服务器 |
| 32B / 72B | 24GB / 48GB+ | 高性能服务器 |
> **AIO 环境注意**：Docker 容器本身约占 300MB，加上 Ollama 模型内存，请确保宿主机有足够的**可用物理内存**，避免系统 OOM Killer 强制终止进程。

### 9.4 WebUI 配置步骤

1. 进入 Neon Crate → 设置 → 推理引擎
2. LLM 提供商选择：`local`
3. 本地 LLM URL：
   - **裸机部署**：`http://localhost:11434/v1/chat/completions`
   - **Docker 内访问宿主机**：`http://host.docker.internal:11434/v1/chat/completions`
4. 本地 LLM Key：`ollama`（固定值）
5. 本地 LLM 模型：`qwen2.5`（或已下载的模型名）
6. 保存配置

### 9.5 Docker Compose 中的 Ollama 网络配置

若 Ollama 运行在宿主机（非容器），Docker 内的 backend 容器通过 `host.docker.internal` 访问：
```yaml
# docker-compose.yml 中 backend 服务追加
extra_hosts:
  - "host.docker.internal:host-gateway"
```
若希望 Ollama 也容器化，可追加服务：
```yaml
  ollama:
    image: ollama/ollama:latest
    container_name: neon-crate-ollama
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"
    networks:
      - neon-crate-net
volumes:
  ollama_data:
```
容器化 Ollama 时，backend 的本地 LLM URL 改为：`http://ollama:11434/v1/chat/completions`
---

## 十、数据持久化与备份策略

> 深度索引：`docs/03_后端模块手册/01_infra/database.md`

### 10.1 关键数据文件清单

```
backend/data/
├── media_database.db   ★★★ 媒体库主数据库（SQLite WAL 模式）
├── config.json         ★★★ 应用配置（含加密 API Key，原子写入保护）
├── secret.key          ★★★ Fernet 主密钥（0o600权限，丢失则所有配置无法解密）
├── auth.json           ★★  管理员账号（bcrypt 哈希，丢失需重新初始化）
├── secure_keys.json    ★★  加密 API 密钥备份
├── posters/            ★   本地海报缓存（可重新刮削下载，非关键）
└── logs/
    └── app.log         ★   滚动日志（10MB × 5 备份，可定期清理）
```
**优先级说明**：★★★ = 必须备份 | ★★ = 建议备份 | ★ = 可选

### 10.2 备份命令

```bash
# 完整数据目录备份
tar -czf neon-crate-backup-$(date +%Y%m%d).tar.gz backend/data/
# 仅备份关键文件（最小集）
mkdir -p backup
cp backend/data/media_database.db backup/
cp backend/data/config.json backup/
cp backend/data/secret.key backup/
cp backend/data/auth.json backup/
# SQLite 热备份（WAL 模式下安全，无需停服）
sqlite3 backend/data/media_database.db ".backup backup/media_database_$(date +%Y%m%d).db"
```

### 10.3 恢复流程

```bash
# 1. 停止服务
docker compose down
# 2. 恢复数据
tar -xzf neon-crate-backup-YYYYMMDD.tar.gz
# 3. 确认 secret.key 权限
chmod 600 backend/data/secret.key
# 4. 重启服务
docker compose up -d
```

### 10.4 日志管理

日志系统由 `RotatingFileHandler` 管理（10MB × 5 备份），无需手动轮转。定期清理旧日志：
```bash
find backend/data/logs/ -name "*.log*" -mtime +7 -delete
```

### 10.5 数据库维护

```bash
# WAL 检查点（释放 WAL 文件磁盘空间）
sqlite3 backend/data/media_database.db "PRAGMA wal_checkpoint(TRUNCATE);"
# 数据库完整性检查
sqlite3 backend/data/media_database.db "PRAGMA integrity_check;"
# 查看数据库大小
du -sh backend/data/media_database.db
```
---

## 十一、故障排查手册

### 11.1 前端 404 / 白屏

**现象**：访问 `http://your-host:8000` 返回 404 或空白页
**排查步骤**：
```bash
# 检查 static 目录是否存在
ls -lh backend/static/index.html
# 检查启动日志
# 应有：[OK] 前端静态文件已挂载: static -> /
# 若有：[INFO] 未找到前端静态目录 static → 需重新构建前端
# 重新构建前端
cd frontend && npm run build && mv out ../backend/static && cd ..
# 重启服务
docker compose restart backend
```

### 11.2 API 请求返回 HTML

**现象**：前端调用 API 收到 HTML 响应而非 JSON
**原因**：API 路径未以 `/api` 开头，被 SPA 回退处理器拦截返回 `index.html`
**解决**：检查前端 `lib/config.ts` 中的 `API_BASE` 常量，确保值为 `/api/v1`。
```bash
# 验证 API 路径
curl http://localhost:8000/api/v1/auth/status   # 正确：返回 JSON
curl http://localhost:8000/auth/status          # 错误：返回 HTML
```

### 11.3 媒体资源 403 / 404

**现象**：海报图片无法加载
**排查步骤**：
```bash
# 检查容器内挂载点
docker compose exec backend ls /storage
# 检查启动日志
# 应有：[OK] 静态资源已挂载: /storage -> /api/v1/assets
# 验证图片代理路径
curl "http://localhost:8000/api/v1/public/image?path=%2Fstorage%2Fposters%2Ftest.jpg"
```
**常见原因**：
- `DOCKER_STORAGE_PATH` 与 volumes 挂载路径不一致
- 宿主机媒体目录权限不足，容器用户无读权限

### 11.4 JWT 401 错误

**现象**：所有受保护 API 请求返回 401 Unauthorized
| 原因 | 解决方案 |
|------|----------|
| Token 过期（默认7天）| 重新登录获取新 Token |
| `JWT_SECRET_KEY` 重启后变更 | 确保 `.env` 中密钥不变，避免每次启动重新生成 |
| `secret.key` 文件丢失 | 
步骤3：构建并启动容器
docker compose up -d --build
# 步骤4：查看启动日志
docker compose logs -f backend
# 步骤5：验证服务
curl http://localhost:8000/health
```
### 8.4 日常运维命令
```bash
# 查看运行状态
docker compose ps
# 查看实时日志
docker compose logs -f backend
# 重启服务
docker compose restart backend
# 停止服务
docker compose down
# 更新部署（重新构建前端后）
rm -rf backend/static
cd frontend && npm run build && mv out ../backend/static && cd ..
docker compose up -d --build backend
# 进入容器 Shell
docker compose exec backend bash
# 查看容器资源占用
docker stats neon-crate-engine
```
### 8.5 数据卷说明
| 宿主机路径 | 容器路径 | 说明 |
|------------|----------|----- |
| `./backend/data` | `/app/data` | 数据库、配置、密钥、海报、日志 |
| `/path/to/your/media` | `/storage` | 媒体文件存储（须与 `DOCKER_STORAGE_PATH` 一致）|
> **重要**：`./backend/data` 目录包含 `secret.key`（Fernet 主密钥）和 `auth.json`（管理员账号），**必须持久化挂载，绝不能删除**，否则所有加密配置将无法解密，需重新初始化。
---
## 十二、部署检查清单
### 12.1 部署前检查
- [ ] Python 3.10+ 已安装
- [ ] Node.js 18+ 已安装（仅构建阶段）
- [ ] `backend/requirements.txt` 依赖已安装
- [ ] `backend/.env` 文件已创建，`JWT_SECRET_KEY` 已替换为强随机值
- [ ] `DOCKER_STORAGE_PATH` 已配置为实际媒体存储路径
### 12.2 前端构建检查
- [ ] `frontend/next.config.js` 已设置 `output: 'export'`
- [ ] `frontend/next.config.js` 已设置 `images: { unoptimized: true }`
- [ ] `frontend/next.config.js` 中已移除 `rewrites` 配置
- [ ] `npm run build` 构建成功，无报错
- [ ] `backend/static/index.html` 文件存在
### 12.3 启动验证检查
- [ ] 启动日志含 `[OK] 前端静态文件已挂载: static -> /`
- [ ] 启动日志含 `[OK] 静态资源已挂载`
- [ ] `GET http://localhost:8000/health` 返回 `{"status": "healthy"}`
- [ ] `GET http://localhost:8000/api/v1/auth/status` 返回 JSON
- [ ] 浏览器访问 `http://localhost:8000` 显示登录/初始化页面
- [ ] 访问 `http://localhost:8000/dashboard` 返回 200（SPA 回退生效）
- [ ] API 404 返回 JSON 而非 HTML
### 12.4 生产安全检查
- [ ] `JWT_SECRET_KEY` 已修改，不使用默认值
- [ ] `DEBUG=False` 已确认
- [ ] `data/secret.key` 文件权限为 `0o600`
- [ ] `data/auth.json` 文件权限为 `0o600`
- [ ] 媒体目录未直接暴露到公网（通过代理访问）
- [ ] Docker volumes 中 `data/` 目录已持久化挂载
### 12.5 功能验证检查
- [ ] 管理员账号初始化成功
- [ ] TMDB API Key 已配置并验证（设置 → API 密钥）
- [ ] 媒体存储路径已配置（设置 → 路径，满足 1+1 约束）
- [ ] 触发手动扫描返回成功响应
- [ ] AI 对话功能可用（已配置 LLM，云端或本地）
---
## 十三、模式对比与选型建议
### 13.1 AIO 模式 vs 分离模式
| 特性 | AIO 模式 | 分离模式 |
|------|----------|---------|
| Python 进程数 | 1 | 1 |
| Node.js 进程 | 不需要 | 需要（开发时）|
| 端口数量 | 1（8000）| 2（3000 + 8000）|
| 内存占用 | ~300MB | ~500MB+ |
| CORS 配置 | 不需要 | 需要 |
| 反向代理 | 不需要 | 需要（或 rewrites）|
| 热重载 | 不支持 | 支持 |
| 前端调试体验 | 差 | 好 |
| 部署复杂度 | 低 | 中 |
| Docker 镜像体积 | 小（无 Node.js）| 大 |
| 适用场景 | 生产部署 | 本地开发 |
### 13.2 部署方案选型
| 场景 | 推荐方案 | 说明 |
|------|----------|------|
| 家庭 NAS（群晖/威联通）| Docker Compose AIO | 资源占用最低，管理最简单 |
| 低配 VPS（1C1G）| 裸机 uvicorn 单进程 | 节省 Docker 开销 |
| 标准 VPS（2C2G+）| Docker Compose + systemd | 稳定性与易维护性均衡 |
| 开机自启服务器 | systemd 服务 | 系统级进程管理 |
| 带 GPU 的本地服务器 | Docker Compose + Ollama 容器 | 最大化 AI 能力 |
| 开发调试环境 | 分离模式（Next.js dev + uvicorn）| 热重载、快速迭代 |
### 13.3 升级部署流程（V1.0 → V1.1）
```bash
# 1. 备份数据（必做）
tar -czf backup-before-upgrade-$(date +%Y%m%d).tar.gz backend/data/
# 2. 拉取最新代码
git pull origin main
# 3. 更新后端依赖
cd backend && pip install -r requirements.txt && cd ..
# 4. 重建前端静态产物
cd frontend && npm install && npm run build && mv out ../backend/static && cd ..
# 5. 重启服务
docker compose up -d --build
# 或
systemctl restart neon-crate
# 6. 验证
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/auth/status
```
**V1.0 → V1.1 升级说明**：
- 数据库自动迁移（`_migrate_plaintext_keys`）：首次启动自动将历史明文 API Key 迁移为 Fernet 加密存储，**无需手动操作**
- AI 规则注入策略变更：改为只在字段为空时注入默认值，不覆盖用户已修改的内容
- 正则规则架构重构：`MediaCleaner` 完全改为从数据库读取规则，若 RegexLab 中规则为空将自动补注 15 条默认值
---

## 总结

### AIO 模式核心要点回顾

| 步骤 | 操作 | 关键点 |
|------|------|--------|
| **1. 前端构建** | `npm run build` | `output: 'export'`，移除 `rewrites` |
| **2. 产物转移** | `mv out ../backend/static` | 目标路径固定为 `backend/static/` |
| **3. 环境配置** | 编辑 `.env` | `JWT_SECRET_KEY` 生产必改 |
| **4. 启动服务** | `uvicorn app.main:app` | 确认日志含 `[OK] 前端静态文件已挂载` |
| **5. 初始化** | 浏览器访问 `:8000` | 创建管理员账号，单次操作 |
| **6. 配置密钥** | 设置页面填入 API Key | TMDB / LLM / 下载器密钥 |

### 架构模块索引

| 本指南章节 | 对应后端模块手册 | 对应前端模块手册 |
|------------|------------------|------------------|
| 环境变量配置 | `01_infra/config.md` | — |
| 数据库初始化 | `01_infra/database.md` | — |
| 安全模块 | `01_infra/security.md` | — |
| 路由接管 / 启动日志 | `main.md` | `01_app/layout.md` |
| 鉴权初始化 | `02_api/auth.md` | `05_context_hooks/context_hooks.md` |
| AIO 静态挂载 | `main.md` | `01_app/pages.md` |
---
**文档结束**
**维护者**：Neon Crate 架构 & DevOps 团队  
**文档版本**：V1.1  
**最后更新**：2026-03-12  
**深度索引来源**：`docs/03_后端模块手册/*` + `docs/04_前端模块手册/*`  
**上一版本**：`06_AIO全栈部署指南_V1.0.md`
