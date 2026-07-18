# Neon Crate

**v1.0.0** — NAS 和家庭媒体服务器的全自动媒体库管理系统。

> 扫描 → 识别 → 获取元数据 → 自动归档 → 查找字幕。

---

## 功能特性

- **完全自动化流程**：从下载到整理入库的完整工作流
- **健壮的元数据处理**：多层级降级系统，优雅处理损坏的 NFO 文件和缺失数据
- **高并发支持**：采用 Singleflight 缓存和速率限制，应对高并发场景
- **AI 驱动的识别**：自然语言界面支持指令和媒体搜索

---

## 核心架构

### 元数据解析（三层防御）

1. **容错读取**：采用 `errors=replace` 编码降级
2. **结构修复**：解析前修复格式错误的 XML
3. **正则提取**：即使 XML 损坏也能恢复关键字段

### TMDB 搜索（降级策略）

`标题 + 年份` → `标题` → `截断标题`

减少 LLM 幻觉，提高匹配准确度。

### 重复检测

基于 IMDb ID 的重复检测，确保每部作品在库中仅有一条记录。

### 自动配置修复

启动时自动填充缺失的配置值，使用合理的默认值。

### 高并发缓存

Singleflight + TTL 机制防止并发海报请求时的资源耗尽。

---

## 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | Next.js 14 + TypeScript + Tailwind CSS |
| 后端 | FastAPI + Python 3.12 |
| 数据库 | SQLite（WAL 模式）|
| 认证 | JWT + bcrypt |
| 加密 | Fernet |
| LLM | OpenAI 兼容 API（DeepSeek / Together / Ollama）|
| 外部服务 | TMDB、OpenSubtitles、Radarr / Sonarr |
| 部署 | Docker Compose |

---

## 快速开始

### Docker Compose（推荐）

```yaml
version: '3.8'
services:
  neon-crate:
    image: x1000qaq/neon-crate:v1.0.0
    container_name: neon-crate
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - /your/downloads:/storage/ready_for_ai
      - /your/media:/storage/media
    environment:
      - JWT_SECRET_KEY=change-me-in-production
      - TMDB_API_KEY=your-api-key
```

启动：

```bash
docker-compose up -d
# 访问：http://localhost:8000
```

### 本地开发

**后端：**

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

**前端：**

```bash
cd frontend
npm install
npm run dev
```

前端开发服务器运行在 `http://localhost:3000`，自动代理 API 请求到 `http://localhost:8000/api/v1`。

---

## 配置

### 必需的环境变量

- `TMDB_API_KEY`：从 https://www.themoviedb.org/settings/api 获取
- `JWT_SECRET_KEY`：生产环境必须修改为强密钥
- `DOCKER_STORAGE_PATH`：容器内的媒体存储路径（默认值：`/storage`）

### 可选配置

- `LLM_PROVIDER`：`deepseek` | `together` | `ollama`
- `LLM_API_KEY`：选定 LLM 提供商的 API 密钥
- `RADARR_URL` / `SONARR_URL`：*arr 服务的 URL 地址
- `LOG_LEVEL`：`DEBUG` | `INFO` | `WARNING`

---

## API 概览

除 `/auth/login` 外，所有端点都需要 JWT 认证。

### AI 助手

- `POST /agent/chat`：发送消息，获取 AI 响应
- `POST /agent/confirm`：确认下载请求

### 任务

- `POST /tasks/scan`：扫描下载目录
- `POST /tasks/scrape_all`：获取 TMDB 元数据
- `POST /tasks/find_subtitles`：搜索字幕
- `GET /tasks/*/status`：检查任务状态

### 系统

- `GET /system/stats`：库统计信息
- `GET /system/logs`：最近日志
- `GET /system/status`：服务状态

---

## 文档

完整文档位于 `/docs` 目录：

- [系统架构](./docs/01_架构设计/01_系统全景.md)
- [后端架构](./docs/01_架构设计/02_后端架构白皮书.md)
- [前端架构](./docs/01_架构设计/03_前端架构白皮书.md)
- [数据契约与 API 规范](./docs/02_数据契约/)
- [部署指南](./docs/04_运维部署/01_AIO部署指南.md)
- [模块参考](./docs/05_模块手册/)

---

## 项目结构

```
Neon-Crate/
├── backend/              # FastAPI 服务
│   ├── app/
│   │   ├── api/          # HTTP 路由
│   │   ├── core/         # 应用初始化
│   │   ├── infra/        # 数据库、配置、安全
│   │   ├── models/       # Pydantic 模型
│   │   └── services/     # 业务逻辑
│   └── data/             # SQLite 数据库（.gitignore 保护）
├── frontend/             # Next.js 应用
│   ├── app/              # 页面
│   ├── components/       # React 组件
│   ├── lib/              # API 客户端、国际化
│   └── out/              # 构建产物（.gitignore 保护）
├── docs/                 # 项目文档
└── docker-compose.yml
```

---

## 开发

1. **后端**：FastAPI 开发模式自动重新加载
2. **前端**：Next.js HMR 保存时自动更新
3. **数据库**：使用 SQLite CLI 或迁移脚本
4. **架构决策**：查阅 `/docs` 目录

---

## 已知限制

- 单个管理员账户（基于 JWT）
- SQLite：适合单用户，不适合高并发写入
- 字幕搜索仅限 OpenSubtitles API

---

## 许可证

MIT

---

## 资源

- [文档](./docs)
- [问题反馈](https://github.com/X1000QAQ/Neon-Crate/issues)
- [GitHub 仓库](https://github.com/X1000QAQ/Neon-Crate)
