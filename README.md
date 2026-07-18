# Neon Crate ⚡️🧠📼

**工业级、全自动、带赛博朋克美学的智能影音归档中枢（v1.0.0）**

> 面向 NAS / 家庭媒体服务器：一键扫描 → AI 识别 → TMDB 元数据刮削 → 自动归档 → 字幕补全。  
> 前端是 **Holographic Void（全息虚空）** 指挥台，后端是带“核安全边界”的工业级流水线。

⚠️ **[AUTHOR NOTE] 碳基与硅基的共生之作**：  
本项目由一名**编程新人**借助 AI（Cursor / 大模型）从零到一构建。它不仅是一个实用的影音工具，更是一场验证“人类想象力 + AI 架构执行力”能否打造出**工业级、高并发、高可用**全栈系统的极客实验。

---

## ✨ Why Neon Crate

- **全自动流水线**：扫描下载源 → 清洗文件名 → 元数据刮削 → 归档落盘 → 字幕补完。
- **工业级健壮性**：对第三方脏数据/脏 NFO 具备极强生存能力（短路优先、兜底必达）。
- **高压不假死**：为高并发请求设计的“单飞缓存（Singleflight）/降载策略”，抵抗图片洪峰与轮询风暴。
- **极致 UI 体验**：60fps 等高扁平树 + VHS 磁带故障特效 + Neural Link 状态栏（全站统一的量子态指令同步）。

---

## 🧱 Core Architecture（硬核底座）

### 🛡️ NFO 三层装甲防御
1. **读取容错**：`errors=replace`，保证“至少读得出来”。
2. **生化清洗**：对毒化 XML 做结构修复，让其重新可解析。
3. **正则兜底**：XML 彻底碎裂时仍抢救 `tmdb_id/imdb_id/title/year`，确保短路链路不断裂。

### 🎯 TMDB 三梯队搜索降级引擎
`Title + Year` → `Title（无 Year）` → `截断 Title（无 Year）`  
**核心价值**：专杀大模型“年份幻觉”等噪声，命中率与稳定性同时可控。

### 🧨 金标准物理防爆护盾
以 IMDb ID 等“金标准”做防重熔断：重复媒体直接进入 `ignored`（已忽略）状态，并继承本地海报锚点，确保 UI 语义稳定不破图。

### 🧬 创世自愈注入（Genesis Healing）
缺失/空值配置不靠“内存兜底”，而是对 `config.json` 执行物理注入：启动即自愈、幂等、可追溯。

### 🚀 高并发单飞缓存（Singleflight）
面对海报图片洪峰等高并发场景，以 TTL + Singleflight 将“每请求打 DB”的放大器削平，告别 FastAPI 线程池饥饿引发的前端假死。

---

## 🌌 Holographic Void（视觉美学）

- **等高扁平树（Flat Hierarchical List）**：电影/剧集统一 Row 渲染模型，层级仅用极简缩进表达，拒绝嵌套地狱。
- **VHS 磁带炸裂故障特效**：`ignored` 任务具备噪点 / 扫描线 / RGB 分离 / 故障印章层。
- **Neural Link 状态栏**：前端 `useNeuralLinkStatus` 全局单例订阅者模式，将量子态/神经链路绑定真实后端轮询，并已接入 i18n 国际化（中英双语）。

---

## 🐳 部署指南（Docker 一键起飞）

镜像已正式推送至 Docker Hub，支持直接拉取部署。

### 方式一：Docker Compose (推荐)
创建 `docker-compose.yml` 文件：

```yaml
version: '3.8'
services:
  neon-crate:
    image: x1000qaq/neon-crate:v1.0.0  # 或使用 latest
    container_name: neon-crate
    restart: unless-stopped
    ports:
      - "8000:8000"
    volumes:
      # 请根据您的实际 NAS 路径进行映射
      - ./data:/app/data
      - /your/downloads:/storage/ready_for_ai
      - /your/media:/storage/media