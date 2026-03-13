# MediaWall — 媒体库主容器

**文件路径**: `frontend/components/media/MediaWall.tsx`  
**组件类型**: `'use client'`

---

## 职责

媒体视图的核心状态管理层，统一管理任务数据获取、过滤、分页和所有操作回调，向子组件提供纯 props 接口。

---

## 状态

| 状态 | 类型 | 说明 |
|------|------|------|
| `tasks` | `Task[]` | 服务端返回的原始任务列表（page_size=99999 全量拉取）|
| `statusFilter` | `string` | 当前状态过滤值 |
| `typeFilter` | `string` | 当前类型过滤值 |
| `searchKeyword` | `string` | 输入框当前值（实时）|
| `debouncedKeyword` | `string` | 防抖后关键词（500ms）|
| `page` | `number` | 当前页码（前端分页）|
| `selectedIds` | `Set<number>` | 已选中任务 ID 集合 |
| `toast` | `string\|null` | 轻提示文本 |
| `purgeModalOpen` | `boolean` | 清空确认弹窗 |
| `batchDeleteModalOpen` | `boolean` | 批量删除确认弹窗 |

---

## 数据流

```
api.getTasks({ page:1, page_size:99999, status, media_type, search })
  └── tasks (全量)
        └── filteredTasks（前端二次过滤 + 排序）
              └── paginatedTasks（前端分页 PAGE_SIZE=20）
                    └── <MediaTable tasks={paginatedTasks} />
```

**全量拉取原因**：前端需要对过滤结果进行正确的总页数计算，避免后端分页与前端过滤不一致。

---

## 过滤与排序

```typescript
const filteredTasks = useMemo(() => {
  let list = [...tasks];
  // 状态过滤（failed 兼容 match failed）
  // 类型过滤（movie / tv）
  // 按 created_at 降序排列（最新在前）
  return list;
}, [tasks, statusFilter, typeFilter]);
```

---

## 操作回调

| 回调 | 说明 |
|------|------|
| `handleRetry(taskId)` | 重置任务为 pending |
| `handleDelete(taskId)` | 单条删除（confirm 确认）|
| `handleBatchDelete()` | 批量删除已选 ID |
| `handlePurge()` | 清空全部（需输入 CONFIRM）|
| `handleScan/Scrape/FindSubs` | 触发后台任务 |
| `toggleSelect/selectAll/invert` | 多选操作 |

---

## 子组件

```
MediaWall
  ├── MediaToolbar   ← 搜索/过滤/任务触发按钮
  ├── MediaTable     ← 任务卡片列表
  └── MediaPagination ← 分页控件
```
