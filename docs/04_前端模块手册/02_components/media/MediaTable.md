# MediaTable — 任务卡片列表

**文件路径**: `frontend/components/media/MediaTable.tsx`  
**组件类型**: `'use client'`

---

## 职责

纯展示组件，将任务数组渲染为全息卡片列表，支持多选、重试、删除操作。

---

## Props

| Prop | 类型 | 说明 |
|------|------|------|
| `loading` | `boolean` | 加载中显示骨架屏 |
| `tasks` | `Task[]` | 当前页任务列表 |
| `selectedIds` | `Set<number>` | 已选中 ID |
| `onToggleSelect` | `(id) => void` | 单选切换 |
| `onSelectAll` | `() => void` | 全选当前页 |
| `onInvertSelection` | `() => void` | 反选当前页 |
| `isAllSelected` | `boolean` | 全选状态 |
| `isSomeSelected` | `boolean` | 半选状态（indeterminate）|
| `onRetry` | `(id) => void` | 重试失败任务 |
| `onDelete` | `(id) => void` | 删除任务 |

---

## 卡片信息层级

```
[复选框] [海报图] [标题区]                          [状态标签] [外部链接] [时间戳] [操作]

标题区：
  displayTitle  ← title + year + S01E01（刮削后）或 file_name（未刮削）
  originalName  ← file_path 末段文件名
  目标路径 (target_path)
  原始路径 (file_path)
```

---

## 标题渲染逻辑

```typescript
// 判断是否有真实刮削标题（排除噪声标签）
const noisePattern = /\b(4k|2160p|1080p|720p|...)\b/i;
const hasRealTitle = !!title && title !== fileName && !noisePattern.test(title);

// 有刮削标题：片名 + 年份 + 季集
// 无刮削标题：直接显示文件名
```

---

## 状态标签颜色

| status | 颜色 |
|--------|------|
| `archived` | `border-cyber-cyan text-cyber-cyan` |
| `failed` | `border-cyber-red text-cyber-red` |
| `ignored` | `border-gray-400 text-gray-400` |
| `pending` / 其他 | `border-cyber-cyan/30 text-cyber-cyan/70` |

---

## 流水线进度条

卡片底部显示三阶段进度条：

| 进度 | 条件 |
|------|------|
| 30% | `status=pending` |
| 60% | `status=archived/scraped` 且字幕未完成 |
| 100% | `status=archived` 且 `sub_status=scraped` |

---

## 海报代理

```typescript
const getPosterUrl = (task) => {
  const path = task.local_poster_path || task.poster_path;
  if (!path) return '/placeholder-poster.jpg';
  if (path.startsWith('http')) return path;  // TMDB 外链直接使用
  return `/api/v1/public/image?path=${encodeURIComponent(path)}`; // 本地路径走代理
};
```

本地路径通过 `SecureImage` 组件携带 JWT 请求。
