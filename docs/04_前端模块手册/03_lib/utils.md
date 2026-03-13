# lib/utils.ts — 工具函数

**文件路径**: `frontend/lib/utils.ts`

---

## 函数速查

### `cn(...inputs)`

```typescript
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

合并 Tailwind 类名，解决条件类名冲突。项目中所有动态 `className` 均通过此函数处理。

**示例**：
```tsx
cn(
  'border border-cyber-cyan text-cyber-cyan',
  isActive && 'bg-cyber-cyan text-black',
  disabled && 'opacity-50'
)
```

---

### `formatDate(dateString)`

```typescript
export function formatDate(dateString: string): string
```

将 ISO 日期字符串格式化为本地化显示格式（`zh-CN` locale）。  
用于 `MediaTable` 中任务卡片的 `created_at` 时间戳展示。

**示例**：
```typescript
formatDate('2026-03-12T10:00:00')  // → '2026/3/12 10:00:00'
```
