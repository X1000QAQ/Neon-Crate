# AiSidebar — Neural Core AI 侧边栏

**文件路径**: `frontend/components/ai/AiSidebar.tsx`  
**组件类型**: `'use client'`  
**层级**: `fixed z-[100]`（侧边主体）+ `z-[110]`（触发轴）

---

## 职责

全局 AI 助手侧边栏，从屏幕右侧滑入，提供与后端 `AIAgent` 的对话界面，支持意图触发和候选列表交互。

---

## 开关机制

```
右边缘触发轴（28px 宽透明条）
  ↓ 点击
isOpen: false → true  （侧边栏从 right:-384px 滑入到 right:4px）
触发轴随之左移到 right:384px
```

登录页（`pathname === '/auth/login'`）直接 `return null`，不渲染。

---

## 消息流

```typescript
// 发送消息
handleSendText(text: string) {
  1. 添加用户消息到 messages
  2. 封死所有已存在的候选按钮（防二次选择）
  3. api.chat(text)
  4. 添加 AI 响应到 messages
  5. 根据 action 触发对应任务
}

// action 处理
ACTION_SCAN    → api.triggerScan()
ACTION_SCRAPE  → api.triggerScrapeAll()
ACTION_SUBTITLE → api.triggerFindSubtitles()
```

---

## 候选列表（__CANDIDATES__）

后端返回含 `__CANDIDATES__` 标记的消息时，解析为可点击按钮列表：

```
"以下是搜索结果：__CANDIDATES__[\"片名A\", \"片名B\", \"片名C\"]"
          ↓ parseCandidates()
 text: "以下是搜索结果："
 candidates: ["片名A", "片名B", "片名C"]
```

只有**最新一条**候选消息的按钮处于激活状态，旧候选消息按钮自动变灰禁用。

---

## 神经波形背景

```typescript
// requestAnimationFrame 循环
setWaveAmplitude(prev => (prev + 0.1) % 100);

// SVG 三条动态 Bézier 曲线
M 0 {200+sin(w*0.1)*30} Q ... T ...
```

三条曲线分别位于面板 1/3、2/3、底部区域，透明度依次降低（1.0 / 0.6 / 0.3）。

---

## 快捷指令

```
/scan    → t('ai_quick_scan')
/analyze → t('ai_quick_scrape')
/failed  → t('ai_quick_failed')
/status  → t('ai_quick_status')
```

空对话状态下显示为 2×2 快捷按钮网格，点击后填充到输入框。

---

## Matrix-drop 动画

每条新消息渲染时触发 60ms 延迟 fade-in 动画（translateY 8px → 0），模拟终端字符逐帧显示效果。
