# Neon Crate ⚡️🧠📼

**工业级、全自动、带赛博朋克美学的智能影音归档中枢（v1.0.0）**

> 面向 NAS / 家庭媒体服务器：一键扫描 → AI 识别 → TMDB 元数据刮削 → 自动归档 → 字幕补全。  
> 前端是 **Holographic Void（全息虚空）** 指挥台，后端是带“核安全边界”的工业级流水线。

---

## ✨ Why Neon Crate

- **全自动流水线**：扫描下载源 → 清洗文件名 → 元数据刮削 → 归档落盘 → 字幕补完
- **工业级健壮性**：对第三方脏数据/脏 NFO 具备生存能力（短路优先、兜底必达）
- **高压不假死**：为高并发请求设计的“单飞缓存（Singleflight）/降载策略”，抵抗图片洪峰与轮询风暴
- **极致 UI 体验**：60fps 等高扁平树 + VHS 磁带故障特效 + Neural Link 状态栏（全站统一）

---

## 🧱 Core Architecture（硬核底座）

### 🛡️ NFO 三层装甲防御

1. **读取容错**：`errors=replace`，保证“至少读得出来”
2. **生化清洗**：对毒化 XML 做结构修复，让其重新可解析
3. **正则兜底**：XML 彻底碎裂时仍抢救 `tmdb_id/imdb_id/title/year`，确保短路链路不断裂

### 🎯 TMDB 三梯队搜索降级引擎

`Title + Year` → `Title（无 Year）` → `截断 Title（无 Year）`  
核心价值：专杀“年份幻觉”等噪声，命中率与稳定性同时可控。

### 🧨 金标准物理防爆护盾

以 IMDb ID 等“金标准”做防重熔断：重复媒体直接进入 `ignored`，并继承本地海报锚点，确保 UI 语义稳定不破图。

### 🧬 创世自愈注入（Genesis Healing）

缺失/空值配置不靠“内存兜底”，而是对 `config.json` 执行**物理注入**：启动即自愈、幂等、可追溯。

### 🚀 高并发单飞缓存（Singleflight）

面对海报图片洪峰等高并发场景，以 **TTL + singleflight** 将“每请求打 DB”的放大器削平，告别 FastAPI 线程池饥饿引发的前端假死。

---

## 🌌 Holographic Void（视觉美学）

- **60fps 等高扁平树（Flat Hierarchical List）**：电影/剧集统一 Row 渲染模型，层级仅用缩进表达
- **VHS 磁带炸裂故障特效**：`ignored` 任务具备噪点/扫描线/RGB 分离/印章层
- **Neural Link 状态栏**：量子态/神经链路绑定真实系统运行态，并已接入 i18n（中英双语）

---

## 🐳 部署极简（Docker 一键）

```bash
docker build -t neon-crate:latest .
docker-compose up -d
```

默认访问（以 compose/镜像实际端口为准）：
- API / 控制面板：`http://localhost:8000`

---

## 🛠️ 本地开发

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend（新终端）
cd frontend
npm install
npm run dev
```

---

## 📚 文档导航

从 `docs/README.md` 进入完整文库索引（架构白皮书 / 数据契约 / 流水线白皮书 / 模块手册）。

---

## 🔐 Safety Red Lines（核安全红线）

- **禁止裸 fetch**：所有 HTTP 调用必须经过 `frontend/lib/api.ts`
- **i18n 动态键值保护**：`status_` / `sub_status_` / `ui_` 前缀属于领域核心动态键，禁止误删
- **路径/清理/锁释放是核安全边界**：涉及 `_validate_path`、核级清理、finally release 的改动必须极度谨慎

---

## 📄 License

MIT

