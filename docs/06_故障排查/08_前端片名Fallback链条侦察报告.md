# 前端片名 Fallback 链条补全 — 侦察报告

**文档编号**：DEV-RECON-008  
**日期**：2026-03-15  
**GitNexus 基准**：commit `da6f881` ✅ up-to-date  
**状态**：✅ 侦察完成，可直接实施，风险极低

---

## 一、流程示意图

### 1.1 当前 displayTitle 计算流程（含问题点）

```
TaskRow 渲染
    │
    ▼
rawName = task.file_name || task.file_path.split('/').pop() || '-'
    │        ↑ 含后缀："沙丘2 (2024).mkv"
    ▼
hasTitle = !!task.title
              && task.title !== rawName
              && !noiseRe.test(task.title)
    │
    ├─ task.title 存在（TMDB 刮削过）→ hasTitle=true
    │       └─ displayTitle = task.title + year + S/E
    │
    └─ task.title 为空（NFO左移/失忆救援，未刮削）→ hasTitle=false
            └─ displayTitle = rawName  ← ⚠️ 显示「沙丘2 (2024).mkv」
                                          task.clean_name="沙丘2" 被完全忽略！
```

### 1.2 当前 useMemo 分组键生成（含问题点）

```
const key = `${mtype}::${(task.title || task.file_name || String(task.id)).trim()}`
                                ↑                ↑
                         title 为空时        直接用文件名（含后缀）
                         clean_name 被跳过！
```

### 1.3 当前 Level 1 TV 折叠标题（含问题点）

```tsx
// MediaGroup 接口
title?: string   ← 只存 task.title，无 clean_name

// useMemo 建组时
title: task.title   ← task.title 为空时 group.title = undefined

// Level 1 渲染
{group.title || group.key.split('::')[1]}
    ↑               ↑
  title 为空    fallback 到 key 的第二段
                （key 是用 task.file_name 生成的，含后缀！）
```

### 1.4 目标流程（修复后）

```
TaskRow:
  hasTitle = !!(task.title || task.clean_name)
               && (title||clean_name) !== rawName
               && !noiseRe.test(title||clean_name)
  displayTitle = task.title || task.clean_name → rawName（兜底）

useMemo key:
  task.title || task.clean_name || task.file_name || String(task.id)

MediaGroup.title:
  task.title || task.clean_name   ← 建组时写入

Level 1 TV 标题:
  group.title || group.key.split('::')[1]  ← key 已用 clean_name 生成，安全
```

---

## 二、精确问题定位

### 问题 1：TaskRow — `hasTitle` 判断忽略 `clean_name`

**位置**：`MediaTable.tsx` ~112–116 行

```typescript
// 当前代码（有 bug）
const hasTitle = !!task.title && task.title !== rawName && !noiseRe.test(task.title);
let displayTitle = hasTitle ? task.title! : rawName;

// 修复后
const _bestName = task.title || task.clean_name;
const hasTitle = !!_bestName && _bestName !== rawName && !noiseRe.test(_bestName);
let displayTitle = hasTitle ? _bestName : rawName;
```

**副作用**：`displayTitle` 后续拼接 `year`/`S01E01` 时用的是 `task.title!`，需同步改为 `_bestName`。

### 问题 2：`useMemo` 分组键缺少 `clean_name`

**位置**：`MediaTable.tsx` ~306 行

```typescript
// 当前代码
const key = `${mtype}::${(task.title || task.file_name || String(task.id)).trim()}`;

// 修复后
const key = `${mtype}::${(task.title || task.clean_name || task.file_name || String(task.id)).trim()}`;
```

### 问题 3：`MediaGroup` 接口不含 `clean_name`，建组时丢失

**位置**：`MediaTable.tsx` ~37 行 `MediaGroup` 接口 + ~313 行建组逻辑

```typescript
// 接口需新增字段
interface MediaGroup {
  // ...existing...
  title?: string;
  clean_name?: string;   // ← 新增
}

// 建组时
map.set(key, {
  // ...existing...
  title: task.title,
  clean_name: task.clean_name,   // ← 新增
});
```

### 问题 4：Level 1 TV 折叠标题 fallback 不含 `clean_name`

**位置**：`MediaTable.tsx` ~459 行

```tsx
// 当前代码
{group.title || group.key.split('::')[1]}

// 修复后（key 已用 clean_name 生成，split 结果正确；但显式加 clean_name 更清晰）
{group.title || group.clean_name || group.key.split('::')[1]}
```

### 问题 5：`SecureImage` alt 属性缺少 `clean_name`

**位置**：~148 行（TaskRow 海报）

```tsx
// 当前代码
alt={task.title || rawName}

// 修复后
alt={task.title || task.clean_name || rawName}
```

---

## 三、`Task` 类型确认

前端 `types/index.ts` 中 `Task` 接口包含 `clean_name?: string` 字段（第 8–20 行区域），
无需修改类型定义，直接使用即可。

---

## 四、修改清单（5 处，均在 `MediaTable.tsx`）

| # | 位置（约行号） | 修改内容 |
|---|--------------|----------|
| 1 | ~112–119 | `hasTitle`/`displayTitle` 计算加入 `clean_name` fallback |
| 2 | ~37–44 | `MediaGroup` 接口新增 `clean_name?: string` |
| 3 | ~306 | `useMemo` key 生成加入 `clean_name` |
| 4 | ~313–320 | 建组时写入 `clean_name: task.clean_name` |
| 5 | ~459 | Level 1 TV 标题渲染加入 `clean_name` fallback |

**无需修改**：`SecureImage.tsx`、后端任何文件、`types/index.ts`

---

## 五、风险评估

| 风险 | 等级 | 说明 |
|------|------|------|
| 分组键变化导致手风琴状态重置 | 极低 | 只在 `task.title` 为空时 key 才变化，正常已刮削任务不受影响 |
| `clean_name` 含后缀（如 `沙丘2.mkv`） | 低 | `clean_name` 由 ScanEngine 清洗，不含后缀；且 `hasTitle` 的 noiseRe 过滤保护 |
| TypeScript 编译错误 | 无 | `Task.clean_name` 已在类型定义中，直接可用 |

---

*Neon Crate 开发团队 | DEV-RECON-008 | 2026-03-15*
