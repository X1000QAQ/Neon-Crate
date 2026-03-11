# AI 侧边栏 - `components/ai/AiSidebar.tsx`

---

## 一、概述

AI 对话侧边栏，悬浮在页面右侧，通过 `ClientShell` 挂载在所有页面上。

---

## 二、核心功能

### 候选列表解析（`__CANDIDATES__`）

后端 DOWNLOAD 意图返回模糊结果时，响应文本末尾附加结构化数据：

```
找到「X」的多个版本，请选择您想要的：__CANDIDATES__["片名 (年份)", ...]
```

`parseCandidates(content)` 函数以 `__CANDIDATES__` 为分隔符切割：
- `text`：标记之前的引导语（后端本地拼接，保证为干净单行文本）
- `candidates`：JSON 解析后的字符串数组，渲染为快捷选择按钮

用户点击候选按钮后，直接发送片名字符串（后端候选拦截优先匹配，不触发新的意图识别）。

### 候选按钮激活/失效逻辑

- **只有最后一条含候选的消息**的按钮处于激活状态（`lastCandidateIdx` 计算）
- 任何新消息发送时（`handleSendText`），**立即封死当前所有候选消息**（将所有含候选的消息 idx 加入 `selectedMsgIdx`），防止用户二次选择
- 已封死的按钮：`disabled`、变灰、`cursor: not-allowed`，硬阻断点击

### 动作指令执行（`action`）

`ChatResponse.action` 字段触发前端动作：

| action 值 | 前端行为 | 提示消息 key |
|---|---|---|
| `ACTION_SCAN` | 调用 `api.triggerScan()` | `ai_scan_triggered` |
| `ACTION_SCRAPE` | 调用 `api.triggerScrapeAll()` | `ai_scrape_triggered` |
| `ACTION_SUBTITLE` | 调用 `api.triggerFindSubtitles()` | `ai_subtitle_triggered` |

每个 action 执行后均会在对话中追加对应的提示消息（通过 `t()` 国际化）。`DOWNLOAD` action 由后端在 agent 内部完成，前端不处理。

### SSE / 流式响应

AI 对话目前使用标准 `POST /agent/chat`（非流式），响应完整返回后一次性渲染。

---

## 三、状态

| 状态 | 说明 |
|---|---|
| `isOpen` | 侧边栏展开/收起 |
| `messages` | 对话历史记录 |
| `loading` | 等待 AI 响应中 |
| `selectedMsgIdx` | 已封死的候选消息 idx 集合（防二次选择）|
| `visibleIdx` | 已完成入场动画的消息 idx 集合 |

---

## 四、注意事项

- 侧边栏通过 `ClientShell` 在 `AuthGuard` 内部渲染，已鉴权才可见
- 候选引导语由后端本地拼接（不走 LLM），前端直接展示 `parsed.text`，无需二次过滤
- `handleSendText` 在入队用户消息前，先扫描所有含候选的消息并批量封死，确保旧候选在新消息发出后立即变灰
- 候选按钮点击后通过 `setSelectedMsgIdx` 标记当前消息为已选，同时 `handleSendText` 的封死逻辑兜底，双重保险防止重复触发

---

*最后更新：2026-03-11*
