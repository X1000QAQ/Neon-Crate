# MediaToolbar — 搜索/过滤/操作工具栏

**文件路径**: `frontend/components/media/MediaToolbar.tsx`  
**组件类型**: `'use client'`

---

## 职责

纯展示组件，提供媒体库的搜索、过滤和批量操作入口，所有回调由 `MediaWall` 传入。

---

## Props

| Prop | 说明 |
|------|------|
| `searchKeyword / onSearchChange` | 搜索关键词双向绑定 |
| `onRefresh / loading` | 刷新按钮 |
| `selectedCount / onBatchDelete` | 批量删除（显示选中数量徽标）|
| `onPurge` | 打开清空确认弹窗 |
| `onScan / scanning` | 触发物理扫描 |
| `onScrapeAll / scraping` | 触发全量刮削 |
| `onFindSubtitles / findingSubs` | 触发字幕补完 |
| `statusFilter / onStatusChange` | 状态过滤下拉 |
| `typeFilter / onTypeChange` | 类型过滤下拉 |

---

## 布局结构

```
[搜索栏面板]
  搜索框 | 刷新 | 批量删除 | 清空数据库

[过滤器面板]
  [过滤器标题]  [扫描] [刮削] [字幕]
  状态下拉      类型下拉
```

---

## 状态过滤选项

| 值 | 说明 |
|----|------|
| `all` | 全部 |
| `pending` | 待处理 |
| `archived` | 已归档 |
| `success` | 成功 |
| `failed` | 失败（含 match failed）|

---

## 危险操作保护

- **批量删除**：`disabled={selectedCount === 0}`，必须先选中才可点击
- **清空数据库**：点击后由 `MediaWall` 弹出二次确认弹窗，需输入 `CONFIRM`
