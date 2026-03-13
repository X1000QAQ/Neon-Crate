# SystemMonitor — 全功能日志监控

**文件路径**: `frontend/components/media/SystemMonitor.tsx`  
**组件类型**: `'use client'`

---

## 职责

Monitor 视图的完整日志监控面板，支持多标签过滤、自动滚动、实时统计，2 秒轮询刷新。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| 标签过滤 | 12 个可独立开关的日志标签 checkbox |
| 自动滚动 | `autoScroll` 开关，默认开启 |
| 清除日志 | 清空本地 `logs` 状态（不影响服务端）|
| 实时统计 | 底部展示 INFO / WARNING / ERROR 各自数量 |

---

## 日志标签

| 标签 | 对应业务 |
|------|----------|
| SCAN | 文件扫描 |
| TMDB | 元数据刮削 |
| SUBTITLE | 字幕下载 |
| ORG | 文件归档 |
| CLEAN | 文件名清洗 |
| LLM | LLM 调用 |
| AI | AI Agent |
| META | 元数据管理 |
| DB | 数据库操作 |
| SECURITY | 鉴权安全 |
| API | 接口调用 |
| ERROR | 错误日志 |

---

## 地址哈希

每条日志左侧显示 4 位十六进制地址（`0xXXXX`），由 `hashToHex()` 基于内容生成，模拟终端内存地址显示风格。

---

## 动画

| 动画名 | 效果 |
|--------|------|
| `matrix-drop` | 新日志条目从上方滑入（translateY -18px → 0）|
| `quantum-flicker` | 日志文字渲染时轻微模糊后清晰 |

---

## 统计栏

底部三格展示当前可见日志数量：
- INFO 数 — `text-cyber-cyan`
- WARNING 数 — `text-cyber-yellow`（>0 时亮色）
- ERROR 数 — `text-cyber-red`
