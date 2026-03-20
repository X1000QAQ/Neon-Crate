# AIO 全栈部署指南

**文档编号**：OPS-001  
**版本**：v1.0.0-Stable  
**最后更新**：2026-03-20  

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
1. SQLite WAL + 建表（v1.0.0 为物理基准线，MIGRATIONS=[]，零迁移补丁）
2. 历史明文密钥迁移（_migrate_sensitive_keys）
3. 创世配置自愈注入（_inject_ai_defaults，Genesis Config Healing）
4. secret.key 不存在 → 自动生成（0o600）
5. 浏览器访问 :8000 → AuthGuard 检测未初始化 → 创建管理员账号
```

**Genesis Config Healing（创世自愈注入）要点**：
- **绕过内存兜底**：不能通过 `get_config()` 判断“是否缺失”，因为 `get_config()` 会用 `DEFAULT_CONFIG` 屏蔽真实空值
- **物理注入到磁盘**：直接读取/写回 `config.json`，对 7 大核心默认值执行“缺啥补啥”（AI 人格、意图路由规则、归档专家规则、去噪正则、支持的媒体/字幕后缀等）
- **幂等安全**：只补缺失项，用户已有的非空值绝不覆盖

正常启动日志：
```
[INFO][DB] 数据库初始化完成 (Baseline Version 1.0.0)
[ConfigRepo] 创世自愈注入完成，补全 7 个字段: ['ai_name', 'ai_persona', ...]
[OK] 前端静态文件已挂载: static -> /   ← AIO 已启用
```

---

## 五、数据库初始化与密钥加密

### 数据库基准线（_init_database）

系统以 **v1.0.0** 为唯一基准线全新建表，`schema_version` 初始值直接写入 `'1.0.0'`，启动时不触发任何迁移补丁。`MIGRATIONS = []` 为空，`_migrate_database` 静默跳过。

**启动日志**：
```
[INFO][DB] 数据库初始化完成 (Baseline Version 1.0.0)
```

如需在未来版本新增字段，在 `_register_migrations()` 中追加 `> 1.0.0` 的迁移条目即可，引擎会自动执行增量迁移并更新 `schema_version`。

### 敏感密钥明文转密文（_migrate_sensitive_keys）

**业务链路**：
```
1. 读取 config.json 文件 -> 
2. 扫描 SENSITIVE_KEYS 列表中的明文密钥 -> 
3. 将非空明文密钥加密后写入 secure_keys.json -> 
4. 清空 config.json 中的明文密钥 -> 
5. 后续读取时，ConfigRepo 会自动从 secure_keys.json 解密
```

**实现细节**：
```python
# db_manager.py: _migrate_sensitive_keys()
def _migrate_sensitive_keys(self):
    if not os.path.exists(self.config_path):
        return
    
    with open(self.config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    settings = config.get("settings", {})
    crypto = get_crypto_manager()
    
    # Step 1: 扫描明文密钥
    keys_to_migrate = {}
    for key in self.SENSITIVE_KEYS:
        value = settings.get(key, "")
        if value and value.strip():
            keys_to_migrate[key] = value
    
    if not keys_to_migrate:
        return  # 无需迁移
    
    # Step 2: 加载现有的加密存储
    secure_data = {}
    if os.path.exists(self.secure_keys_path):
        with open(self.secure_keys_path, "r", encoding="utf-8") as f:
            secure_data = json.load(f)
    
    # Step 3: 加密并存储密钥
    for key, value in keys_to_migrate.items():
        encrypted = crypto.encrypt_api_key(value)
        secure_data[key] = encrypted
        settings[key] = ""  # 清空明文
    
    # Step 4: 原子写入加密文件
    with open(self.secure_keys_path, "w", encoding="utf-8") as f:
        json.dump(secure_data, f, indent=4)
    
    # Step 5: 原子写入配置文件
    with open(self.config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    logger.info(f"[DB] 已迁移 {len(keys_to_migrate)} 个敏感密钥到加密存储")
```

**幂等性**：多次执行不会重复迁移（已加密的密钥会被跳过）。

**启动日志示例**：
```
[INFO][DB] 已迁移 3 个敏感密钥到加密存储
[INFO][DB] 敏感密钥迁移完成
```

---

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
| SPA 刷新 404 | SPA 回退未生效 | 见下方「常见问题」→ SPA 路由回退 |
| 局域网设备 API 返回 403 | 请求未携带 JWT Token 或 CORS 被拦截 | 见下方「常见问题」→ 局域网 403 访问限制 |

---

## 十、常见问题（FAQ）

### SPA 路由回退（SPA 404 修复）

**现象**：直接访问 `http://IP:8000/auth/login` 返回 404，但访问 `http://IP:8000/` 正常。

**根因**：Next.js `output: 'export'` 生成的是纯静态文件。FastAPI 的 `StaticFiles` 挂载在 `/` 时，
直接访问子路径（如 `/auth/login`）会在磁盘上寻找名为 `auth/login` 的物理文件，找不到则触发 404。
此外，若 `index.html` 使用相对路径定位，Docker 容器内 CWD 不确定时也会找不到文件。

**已修复内容（`backend/app/core/app_factory.py`）**：

1. **绝对路径定位**：`spa_fallback_handler` 中改用 `Path(__file__).resolve()` 计算 `index.html` 绝对路径，
   不再依赖容器运行时 CWD。
2. **静态挂载绝对路径**：`_mount_static_resources` 中 `StaticFiles` 挂载同样使用绝对路径。
3. **双重保障**：`StaticFiles(html=True)` 自动处理已知路径；`404 exception_handler` 作为兜底，
   对所有非 `/api` 路径的 404 统一返回 `index.html`。

**验证方法**：
```bash
# 直接访问子路由，应返回 200 并返回 index.html 内容
curl -I http://<NAS-IP>:8000/auth/login
# 期望：HTTP/1.1 200 OK
```

**Next.js `trailingSlash` 注意事项**：如启用 `trailingSlash: true`，`/auth/login` 会生成为
`auth/login/index.html`，FastAPI `StaticFiles(html=True)` 可自动识别目录下的 `index.html`，无需额外配置。

---

### 局域网 403 访问限制

**现象**：Unraid 终端日志显示来自 `192.168.x.x` 的请求被 `403 Forbidden` 拦截：
```
INFO: 192.168.0.208:6434 - "GET /api/v1/system/logs HTTP/1.1" 403 Forbidden
```

**根因分析**：

| 根因 | 说明 |
|------|------|
| **HTTPBearer 默认行为** | FastAPI `HTTPBearer()` 在请求缺少 `Authorization` 头时自动返回 **403**（非 401），语义不准确 |
| **CORS 配置冲突** | 旧配置 `allow_origins=["http://localhost:3000"]` 不包含局域网 IP，浏览器预检请求被拒 |
| **credentials 冲突** | `allow_origins=["*"]` 与 `allow_credentials=True` 不兼容，FastAPI 会静默降级或报错 |

**已修复内容**：

1. **`backend/app/api/auth.py`**：
   - `HTTPBearer(auto_error=False)`：缺少 token 时不自动抛 403，而是传入 `None`
   - `get_current_user` 统一处理 `None` credentials，返回标准 **401** + `WWW-Authenticate: Bearer` 头

2. **`backend/app/infra/config/__init__.py`**：
   - `CORS_ORIGINS` 默认值改为 `["*"]`，放行所有来源（AIO 同域部署，CORS 实际不触发）

3. **`backend/app/core/app_factory.py`**：
   - `allow_credentials=False`（与 `allow_origins=["*"]` 兼容；JWT 走 header，无需 Cookie）

**重要说明**：403 的本质是**客户端没有携带 JWT Token**（未登录或 Token 过期），而非服务端拦截局域网 IP。
修复后行为变更：未认证请求返回 **401**，客户端（前端 `AuthGuard`）检测到 401 后自动跳转登录页。

**验证方法**：
```bash
# 未携带 token，应返回 401（修复前为 403）
curl -I http://<NAS-IP>:8000/api/v1/system/logs
# 期望：HTTP/1.1 401 Unauthorized

# 携带有效 token，应返回 200
curl -H "Authorization: Bearer <your-token>" http://<NAS-IP>:8000/api/v1/system/logs
# 期望：HTTP/1.1 200 OK
```

---

## 十一、部署检查清单

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

---

## 十二、变更日志

### 2026-03-15 — 生产就绪修复批次

#### SPA 路由回退（404）
- **文件**：`backend/app/core/app_factory.py`
- `spa_fallback_handler` 改用 `Path(__file__).resolve()` 绝对路径定位 `index.html`，消除 Docker CWD 不确定导致的 404
- `_mount_static_resources` 的 `StaticFiles` 挂载同样改用绝对路径

#### 局域网鉴权 403 → 401（auth.py / config）
- **文件**：`backend/app/api/auth.py`
  - `HTTPBearer(auto_error=False)`：无 token 时不自动抛 403，由 `get_current_user` 统一返回 401
  - 新增 `WWW-Authenticate: Bearer` 响应头，符合 RFC 规范
- **文件**：`backend/app/infra/config/__init__.py`
  - `CORS_ORIGINS` 默认值改为 `["*"]`，放行所有局域网来源
- **文件**：`backend/app/core/app_factory.py`
  - `allow_credentials=False`（与 `allow_origins=["*"]` 兼容，JWT 走 Authorization header）

#### 登录页 401 轮询噪音（前端架构）
- **文件**：`frontend/components/common/AuthGuard.tsx`
  - 新增 `authenticatedWrapper` prop：只在 `isAuthenticated=true` 时用 Wrapper 包裹 children
  - `/auth/login` 路径直接渲染裸 children，跳过 Wrapper
- **文件**：`frontend/components/common/ClientShell.tsx`
  - 新增 `AuthenticatedShell` 内部组件（包含 `SettingsProvider` + `LogProvider` + `AiSidebar`）
  - 通过 `authenticatedWrapper={AuthenticatedShell}` 传入 `AuthGuard`
  - **效果**：`SettingsProvider` / `LogProvider` 只在认证通过后挂载，登录页零 API 轮询

#### DB Schema 基准线（v1.0.0）
- **文件**：`backend/app/infra/database/db_manager.py`
  - `schema_version` 初始值 `'1.0.0'`，启动日志：`[INFO][DB] 数据库初始化完成 (Baseline Version 1.0.0)`
  - `MIGRATIONS = []`，新安装不触发任何迁移补丁
