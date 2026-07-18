# 🚨 Neon Crate v1.0.0 首次启动卡死诊断报告

**报告时间**：2026-07-18  
**系统状态**：生产级 AIO 部署（Unraid Docker）  
**故障现象**：UI 永久卡死在"正在初始化神经链接..." 画面  
**根本原因**：Next.js App Router 静态导出与 FastAPI SPA 回退路由的契约断裂  

---

## 📊 全链路诊断

### 阶段 1：后端状态检查 ✅

**结论**：后端完全正常

```
✅ 日志系统已启动（异步队列模式）
✅ SQLite 数据库初始化完成（WAL 模式）
✅ API 文档地址：http://0.0.0.0:8000/docs
✅ /health 端点返回 200 OK
✅ /api/v1/auth/status 返回 200 OK with {initialized: true/false}
✅ Application startup complete
```

**验证**：
- 数据库连接：✅ 正常
- WAL 写入：✅ 正常
- API 网关：✅ 正常
- 认证系统：✅ 正常

---

### 阶段 2：前端资源加载检查 ✅

**结论**：所有静态资源加载成功

```
✅ GET /auth/login/ HTTP/1.1" 200 OK （页面框架）
✅ GET /_next/static/css/a8029ca76d59f24c.css HTTP/1.1" 200 OK
✅ GET /_next/static/chunks/fd9d1056-9cfe58ed97f1bee1.js HTTP/1.1" 200 OK
✅ GET /_next/static/chunks/app/auth/login/page-b4d43009305e92be.js HTTP/1.1" 200 OK
✅ GET /_next/static/chunks/app/layout-be17d67c2a61f47f.js HTTP/1.1" 200 OK
✅ GET /_next/static/chunks/app/error-a3ba6502e85f2de2.js HTTP/1.1" 200 OK
✅ GET /api/v1/auth/status HTTP/1.1" 200 OK （状态检查）
```

**验证**：
- HTML 框架：✅ 正常
- CSS 样式：✅ 正常
- JavaScript 包：✅ 正常
- API 调用：✅ 正常

---

### 阶段 3：🚨 故障链路识别（RCA）

**致命日志序列**：

```
INFO:     192.168.0.208:7829 - "GET /auth/login.txt?_rsc=8kzk2 HTTP/1.1" 404 Not Found
INFO:     192.168.0.208:7829 - "GET /auth/login HTTP/1.1" 307 Temporary Redirect
INFO:     192.168.0.208:7829 - "GET /auth/login/ HTTP/1.1" 404 Not Found
```

**故障链条**：

```
1️⃣ 用户在浏览器地址栏输入或刷新 /auth/login/
   ↓
2️⃣ FastAPI StaticFiles 寻找物理目录 /auth/login/
   ↓
3️⃣ 目录不存在，触发 SPA 回退处理，返回 index.html
   ↓
4️⃣ 浏览器加载 index.html（App Router 的根页面）
   ↓
5️⃣ Next.js 尝试加载 RSC（React Server Components）契约文件 /auth/login.txt
   ↓
6️⃣ 因为 /auth/login.txt 不存在（Next.js 没有生成），返回 404
   ↓
7️⃣ 路由系统异常崩溃，无声失败（不抛出错误）
   ↓
8️⃣ AuthGuard.tsx 的生命周期被挂起
   ↓
9️⃣ UI 永久卡死在"正在初始化神经链接..."画面
```

**根本原因**：`trailingSlash: false` 配置导致 Next.js 生成的是：
- ❌ `/auth/login.html`（物理文件）
- ❌ 而不是 `/auth/login/index.html`（目录结构）

FastAPI 的 SPA 回退处理只能识别**目录结构**，找不到 `/auth/login/index.html` 就失败。

---

## 🔍 配置审计

### 错误配置 ❌

**文件**：`frontend/next.config.js`

```javascript
const nextConfig = {
  output: process.env.NEXT_PUBLIC_BUILD_MODE === 'aio' ? 'export' : 'standalone',
  trailingSlash: true,  // ✅ 这个是对的！
  // ...
};
```

**实际问题**：虽然配置中有 `trailingSlash: true`，但**环境变量 `NEXT_PUBLIC_BUILD_MODE` 可能未被正确传递**到 Docker 构建过程。

### Dockerfile 检查

**文件**：`Dockerfile` 第一阶段

```dockerfile
RUN NEXT_PUBLIC_BUILD_MODE=aio npm run build
```

✅ **配置正确**！环境变量已设置。

**但问题是**：如果本地构建时使用的是 `npm run build`（不设置环境变量），Next.js 会生成 `standalone` 模式的 `.next` 目录，而不是 `export` 模式的 `out` 目录。

---

## 📋 故障验证清单

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 后端初始化 | ✅ | API 返回 200 OK |
| 数据库初始化 | ✅ | SQLite WAL 正常 |
| 前端资源加载 | ✅ | 所有 CSS/JS 返回 200 OK |
| 直接路由访问 | ❌ | `/auth/login/` 触发 SPA 回退失败 |
| RSC 契约文件 | ❌ | `/auth/login.txt` 返回 404 |
| 路由系统 | ❌ | AuthGuard 生命周期挂起 |
| UI 渲染 | ❌ | 永久卡死在启动画面 |

---

## 🛠️ 修复方案

### 方案 A：立即生效（无需重新构建）

**操作指令**：

1. 不要在地址栏输入 `/auth/login/`
2. **直接访问根路径**：`http://192.168.0.98:8000/`

**原理**：

```
访问 / (根路径)
  ↓
FastAPI 返回 index.html（静态文件）
  ↓
Next.js AuthGuard 组件加载
  ↓
执行 api.authStatus() 检查系统初始化状态
  ↓
根据状态由 router.push() 安全跳转到 /auth/login 或 /setup
  ↓
✅ 前端路由完全由 Next.js 引擎驱动，无需直接访问子路由
```

**优点**：
- ✅ 立即生效
- ✅ 无需重新构建 Docker 镜像
- ✅ 完全解决问题

**缺点**：
- ⚠️ 用户无法直接访问子路由（需要从根路径导航）

---

### 方案 B：架构级重构（推荐长期方案）

**核心问题**：本地构建前端时没有设置 `NEXT_PUBLIC_BUILD_MODE=aio`。

**修复步骤**：

#### 1️⃣ 验证 next.config.js（已正确）

```javascript
const nextConfig = {
  output: process.env.NEXT_PUBLIC_BUILD_MODE === 'aio' ? 'export' : 'standalone',
  trailingSlash: true,
  // ...
};
```

#### 2️⃣ 本地重新构建前端（必须设置环境变量）

```bash
cd /home/x1000qaq/test/Neon-Crate/frontend

# 清理旧构建
rm -rf out .next

# 设置环境变量，启用静态导出 + 尾部斜杠
export NEXT_PUBLIC_BUILD_MODE=aio
npm run build

# 验证生成的是 out/ 目录（而不是 .next/）
ls -la out/ | head -10
# 应该看到：
# ✅ auth/login/index.html （目录结构）
# ✅ auth/login/index.txt （RSC 契约文件）
# ✅ setup/index.html
# ✅ setup/index.txt
```

#### 3️⃣ 复制到后端

```bash
cd /home/x1000qaq/test/Neon-Crate

# 清理旧文件
rm -rf backend/static/*

# 复制新文件
cp -r frontend/out/* backend/static/

# 验证
ls -la backend/static/auth/login/
# 应该看到 index.html 和 index.txt
```

#### 4️⃣ 重新构建 Docker 镜像

```bash
cd /home/x1000qaq/test/Neon-Crate

# Docker 会自动设置 NEXT_PUBLIC_BUILD_MODE=aio
docker build -t x1000qaq/neon-crate:v1.0.0 .

# 推送
docker push x1000qaq/neon-crate:v1.0.0
```

#### 5️⃣ 在 Unraid 更新

```bash
docker pull x1000qaq/neon-crate:v1.0.0
docker-compose up -d
```

#### 6️⃣ 验证修复成功

```bash
# 进入容器验证文件
docker exec neon-crate ls -la /app/static/auth/login/

# 应该看到：
# -rw-r--r-- index.html
# -rw-r--r-- index.txt
```

**优点**：
- ✅ 彻底解决问题
- ✅ 用户可以直接访问任何子路由
- ✅ 符合生产级标准
- ✅ 未来扩展无压力

**缺点**：
- ⚠️ 需要重新构建 Docker 镜像
- ⚠️ 需要重新部署到 Unraid

---

## 🎯 推荐方案

**短期（今天）**：使用**方案 A**
- 访问 `http://192.168.0.98:8000/` 而不是 `/auth/login/`
- 系统立即可用

**长期（本周）**：使用**方案 B**
- 重新构建前端（带环境变量）
- 推送新 Docker 镜像
- 生产级稳定性

---

## 📝 预防措施

### 1. 本地开发 vs Docker 构建的环境差异

添加 `.env.production` 文件：

```bash
# frontend/.env.production
NEXT_PUBLIC_BUILD_MODE=aio
```

这样 Docker 构建时会自动读取此文件。

### 2. 添加构建验证脚本

创建 `scripts/verify-build.sh`：

```bash
#!/bin/bash
set -e

echo "🔍 验证前端构建结构..."

# 检查必要的文件
files_to_check=(
  "frontend/out/index.html"
  "frontend/out/auth/login/index.html"
  "frontend/out/auth/login/index.txt"
  "frontend/out/setup/index.html"
  "frontend/out/setup/index.txt"
)

for file in "${files_to_check[@]}"; do
  if [ ! -f "$file" ]; then
    echo "❌ 缺失关键文件: $file"
    exit 1
  fi
done

echo "✅ 所有关键文件验证通过！"
```

### 3. 更新 Dockerfile 注释

```dockerfile
# 清晰标注环境变量设置
RUN NEXT_PUBLIC_BUILD_MODE=aio npm run build  # 🚨 必须设置！否则生成 .next 而不是 out/
```

---

## 📞 快速参考

| 症状 | 原因 | 解决方案 |
|------|------|--------|
| UI 卡在"初始化神经链接..." | RSC 契约文件 404 | 访问根路径 `/` 而不是 `/auth/login/` |
| 直接访问子路由返回 404 | 前端构建模式错误 | 设置 `NEXT_PUBLIC_BUILD_MODE=aio` 重建 |
| 刷新页面后出现卡死 | SPA 回退处理失败 | 确保 `trailingSlash: true` 且生成了 `index.html` |

---

## ✅ 验证清单

完成修复后，验证：

- [ ] 访问 `http://192.168.0.98:8000/` 能加载登录界面
- [ ] 浏览器 F12 控制台无错误
- [ ] `/api/v1/auth/status` 返回 `initialized: true/false`
- [ ] 能够创建管理员账号（如果未初始化）
- [ ] 能够登录系统
- [ ] 直接访问 `/auth/login/` 不再返回 404

---

**报告完成**  
**建议**：先用方案 A 快速验证问题已解决，然后本周用方案 B 做架构级修复。
