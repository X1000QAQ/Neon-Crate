# AIO 全栈部署指南

**文档编号**：OPS-001  
**版本**：v1.0.0-Stable  
**最后更新**：2026-03-14  

---

## 一、AIO 模式原理

```
传统模式：浏览器 → Next.js:3000 → FastAPI:8000
AIO 模式：浏览器 → FastAPI:8000
                    ├─ /api/v1/* → API 路由
                    └─ /*        → static/ 前端静态资源
```

**优势**：单进程、单端口、无 CORS、无 Node.js 运行时、内存约 300MB。

---

## 二、前端构建

```bash
cd frontend && npm install && npm run build
mv out ../backend/static
```

`next.config.js` 关键配置：
```javascript
const nextConfig = {
  output: 'export',
  images: { unoptimized: true },
  // 禁止保留 rewrites
}
```

---

## 三、环境变量

| 变量 | 默认值 | 生产必改 |
|------|--------|----------|
| `JWT_SECRET_KEY` | `"your-secret-key..."` | **是** |
| `DOCKER_STORAGE_PATH` | `"/storage"` | **是** |

> **⚠️ 前端环境变量重要说明**：`NEXT_PUBLIC_API_BASE` 在 `next build` 时被**编译进静态 bundle**，运行时无法更改。
> - AIO 生产构建：**不设置**此变量，走默认值 `/api/v1`（相对路径），适配任意 IP 访问
> - 本地开发：在 `frontend/.env.development.local` 中设置 `NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1`
> - **严禁**在 `frontend/.env.local` 中写死 `http://localhost:8000`，否则 Docker 镜像构建后局域网设备无法访问图片

```bash
python3 -c "import secrets; print(secrets.token_hex(64))"
```

---

## 四、首次启动初始化

```
启动时自动执行：
1. SQLite WAL + 建表 + 历史明文密钥迁移 + 注入 AI 规则/15条正则
2. secret.key 不存在 → 自动生成（0o600）
3. 浏览器访问 :8000 → AuthGuard 检测未初始化 → 创建管理员账号
```

正常启动日志：
```
[OK] 前端静态文件已挂载: static -> /   ← AIO 已启用
[OK] AI 规则注入完成
```

---

## 五、启动方案

```bash
# 方案 A：直接启动
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 方案 B：多进程
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

systemd 服务文件（`/etc/systemd/system/neon-crate.service`）：
```ini
[Service]
WorkingDirectory=/path/to/backend
EnvironmentFile=/path/to/backend/.env
ExecStart=/usr/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
```

---

## 六、Docker 多阶段构建部署（推荐）

> **[2026-03-15 架构升级]** 已迁移至 AIO 多阶段构建，废弃双容器方案。

### 架构对比

| 方案 | 容器数 | 端口数 | 内存开销 | 跨域 | NAS 友好 |
|------|--------|--------|----------|------|----------|
| ~~旧：双容器~~ | ~~2~~ | ~~2（3000+8000）~~ | ~~+200MB Node.js~~ | ~~需要 CORS~~ | ~~❌~~ |
| **新：AIO 单容器** | **1** | **1（8000）** | **~300MB** | **零跨域** | **✅** |

### 多阶段构建原理

```
第一阶段（Node.js 20）：
  frontend/ 源码 → npm run build → out/（Next.js 静态产物）

第二阶段（Python 3.12）：
  backend/ 源码 + out/ → /app/static/（FastAPI StaticFiles 托管）
  单端口 8000 同时响应 /api/v1/* 和 /* 静态资源
```

### 一键部署

```bash
# 在项目根目录执行（Dockerfile 和 docker-compose.yml 均位于根目录）
export JWT_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(64))')
docker compose up -d --build
curl http://localhost:8000/health
```

### docker-compose.yml（AIO 极简版）

```yaml
version: '3.8'

services:
  neon-crate:
    build:
      context: .
      dockerfile: Dockerfile
    image: neon-crate:v1.0.0-stable
    container_name: neon-crate
    ports:
      - "8000:8000"          # 🚀 单端口：前端 + API 全部在此
    volumes:
      - ./data:/app/data     # 🚨 数据持久化防线
      - /path/to/your/storage:/storage  # 🚨 NAS 媒体目录
    environment:
      - JWT_SECRET_KEY=${JWT_SECRET_KEY:-change-me-in-production-to-a-secure-key}
      - DOCKER_STORAGE_PATH=/storage
    restart: unless-stopped
```

### next.config.js 关键配置

```javascript
const nextConfig = {
  output: 'export',   // 🚨 必须：生成静态产物 out/
  // ⚠️ output: 'export' 与 rewrites() 不兼容，禁止添加代理规则
};
```

### API 路径规范（AIO 模式）

```typescript
// ✅ 正确：使用相对路径，AIO 模式下无跨域问题
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';

// ❌ 错误：写死 localhost 导致局域网跨设备访问失败
// export const API_BASE = 'http://localhost:8000/api/v1';
```

**本地开发配置**（仅 `next dev` 时生效，不影响 `next build`）：
```bash
# frontend/.env.development.local（不提交 git）
NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1
```

**AIO 生产构建**：不设置 `NEXT_PUBLIC_API_BASE`，`API_BASE` 自动降级为 `/api/v1` 相对路径。

---

## 七、Ollama 本地 LLM

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5
```

WebUI 配置：LLM 提供商=`local`，URL=`http://host.docker.internal:11434/v1/chat/completions`，Key=`ollama`。

内存建议：7B ≥ 8GB，14B ≥ 16GB。

---

## 八、数据持久化

| 文件 | 优先级 | 说明 |
|------|--------|------|
| `media_database.db` | ★★★ | 媒体库主数据库 |
| `config.json` | ★★★ | 含加密 API Key |
| `secret.key` | ★★★ | 丢失则所有配置无法解密 |
| `auth.json` | ★★ | 管理员账号 |
| `posters/` | ★ | 可重新刮削恢复 |

```bash
tar -czf backup-$(date +%Y%m%d).tar.gz backend/data/
```

---

## 九、故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 访问 :8000 返回 404 | `static/` 不存在 | 重新构建前端 |
| API 返回 HTML | API_BASE 配置错误 | 检查 `lib/config.ts` |
| 海报 403 | `DOCKER_STORAGE_PATH` 与 volumes 不一致 | 对齐路径配置 |
| 海报 401 | AIO 模式下图片请求未携带 token | 确认 `SecureImage` 使用 fetch+token，不用 `<img src>` 直接渲染 |
| 局域网设备海报不显示 | `.env.local` 写死 `http://localhost:8000`，被编译进 bundle | 删除 `.env.local` 的绝对路径，改用 `.env.development.local` 仅本地开发生效 |
| 401 全站 | `secret.key` 变更导致 JWT 失效 | 重新登录 |
| SPA 刷新 404 | SPA 回退未生效 | 检查 `main.py` 404 handler |

---

## 十、部署检查清单

- [ ] 根目录 `Dockerfile` 存在（多阶段构建版）
- [ ] `frontend/next.config.js` 中 `output: 'export'` 已启用
- [ ] `frontend/.env.local` 中**未设置** `NEXT_PUBLIC_API_BASE`（或值为空），AIO 构建使用相对路径
- [ ] 本地开发的 `NEXT_PUBLIC_API_BASE=http://localhost:8000/api/v1` 已移至 `frontend/.env.development.local`
- [ ] `docker-compose.yml` 只有 `neon-crate` 单个服务
- [ ] `.env` 或环境变量中 `JWT_SECRET_KEY` 已替换为强随机值
- [ ] `DOCKER_STORAGE_PATH` 已配置为实际媒体路径
- [ ] 构建成功后启动日志含 `[OK] 前端静态文件已挂载`
- [ ] `GET /health` 返回 `{"status": "online"}`
- [ ] 浏览器访问 `:8000` 显示登录/初始化页
- [ ] `data/secret.key` 权限为 `0o600`
- [ ] Docker volumes 中 `data/` 已持久化挂载
- [ ] 局域网其他设备通过 `http://<NAS-IP>:8000` 可正常访问

*Neon Crate DevOps 团队 | v1.0.0-Stable | 2026-03-15*
