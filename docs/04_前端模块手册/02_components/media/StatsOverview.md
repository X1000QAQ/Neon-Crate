# StatsOverview — 统计卡片 + 指令中心

**文件路径**: `frontend/components/media/StatsOverview.tsx`  
**组件类型**: `'use client'`

---

## 职责

仪表盘视图的核心组件，展示四项媒体库统计数据，并提供扫描/刮削/字幕三个快捷操作按钮。

---

## 统计卡片

| 卡片 | 数据来源 | 图标 |
|------|----------|------|
| 电影总数 | `stats.movies` | `Film` |
| 剧集总数 | `stats.tv_shows` | `Tv` |
| 待处理 | `stats.pending` | `Clock` |
| 已完成 | `stats.completed` | `CheckCircle` |

---

## 数据刷新策略

```typescript
useEffect(() => {
  loadStats();
  // 不轮询，避免频繁读库
  // 扫描/刮削完成后由操作回调主动刷新
}, []);
```

扫描触发后额外启动 `scanBoostTimerRef`：每 1.5 秒刷新一次，持续 30 秒，以实时反映扫描进度。

---

## COMMAND CENTER（指令中心）

三个操作按钮，均使用 `async/await` + loading 状态：

| 按钮 | 图标 | API 调用 |
|------|------|----------|
| 扫描 | `Radar` | `api.triggerScan()` |
| 刮削 | `Wand2` | `api.triggerScrapeAll()` |
| 字幕 | `Subtitles` | `api.triggerFindSubtitles()` |

触发后按钮进入 `disabled` 状态，完成后自动恢复并刷新统计数据。

---

## 动画

统计卡片使用 CSS `hologram-float` 动画（上下浮动 10px），四个卡片各有 0.5s 延迟偏移，形成错落感。
