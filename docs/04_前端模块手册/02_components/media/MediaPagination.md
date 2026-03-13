# MediaPagination — 分页控件

**文件路径**: `frontend/components/media/MediaPagination.tsx`  
**组件类型**: `'use client'`

---

## 职责

纯展示分页组件，当 `totalItems=0` 或 `totalPages<=1` 时自动隐藏（`return null`）。

---

## Props

| Prop | 类型 | 说明 |
|------|------|------|
| `currentPage` | `number` | 当前页码 |
| `totalPages` | `number` | 总页数 |
| `totalItems` | `number` | 过滤后总条目数 |
| `onPageChange` | `(page) => void` | 页码变更回调 |

---

## 页码显示策略

最多显示 5 个页码按钮（`maxVisible=5`）：

| 当前页 | 显示范围 |
|--------|----------|
| `<= 3` | 1 ~ 5 |
| `>= totalPages-2` | `totalPages-4` ~ `totalPages` |
| 其他 | `currentPage-2` ~ `currentPage+2` |

---

## 样式

- 激活页码：`bg-cyber-cyan text-black`，`boxShadow: 0 0 30px rgba(6,182,212,0.8)`
- 非激活页码：透明底 + 霓虹青边框，悬停时反转色
- 上一页/下一页：`ChevronLeft` / `ChevronRight` 图标按钮
