# MiniLog — 仪表盘日志流

**文件路径**: `frontend/components/media/MiniLog.tsx`  
**组件类型**: `'use client'`

---

## 职责

仪表盘底部的轻量日志展示组件，3 秒轮询最新业务日志，过滤噪声后展示最多 50 条。

---

## 轮询配置

| 常量 | 值 | 说明 |
|------|-----|------|
| `MINI_LOG_LINES` | 50 | 最大显示行数 |
| `POLL_INTERVAL_MS` | 3000 | 轮询间隔（ms）|
| `MIN_DISPLAY_LINES` | 8 | 最少显示行数（不足则补占位）|

---

## 过滤规则

**黑名单**（高频噪声日志，过滤掉）：
- `成功获取系统配置`
- `GET /api/v1/tasks`
- `GET /api/v1/system/stats`
- `搜索关键词`
- `[API] 返回任务数`

**白名单**（只显示含以下标签的日志）：
`[SCAN]` `[TMDB]` `[SUBTITLE]` `[ORG]` `[CLEAN]` `[LLM]` `[AI]` `[AI-EXEC]` `[META]` `[DB]` `[SECURITY]` `[API]` `[ERROR]` `[WARNING]`

---

## 占位日志

过滤后不足 8 条时，自动补充科幻风格占位文本：
```
"Holographic matrix stabilized"
"Scanning deep space coordinates"
"Signal detected at quantum layer"
...（共 8 条轮转）
```

---

## 日志等级颜色

| 等级 | 颜色 |
|------|------|
| `ERROR` | `text-cyber-red` |
| `WARNING` | `text-cyber-yellow` |
| `DEBUG` | `text-cyber-cyan/40` |
| `INFO` / 其他 | `text-cyber-cyan` |
