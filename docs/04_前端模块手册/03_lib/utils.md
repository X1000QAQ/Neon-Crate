# 工具函数 - `lib/utils.ts` + `lib/config.ts` + `lib/apiError.ts`

---

## 一、`lib/utils.ts`

### `cn(...inputs: ClassValue[]) -> string`

Tailwind CSS 类名合并工具，组合 `clsx` + `tailwind-merge`。

```typescript
cn('text-cyan border', isActive && 'bg-cyan')  // 合并并去重 Tailwind 类
```

### `formatDate(dateString: string) -> string`

兼容多种后端时间格式的日期格式化函数：
- 处理逗号分隔格式：`"2024-03-09, 14:30:00"`
- 处理空格分隔格式：`"2024-03-09 14:30:00"`
- 处理 SQLite 毫秒格式：`"2024-03-09 14:30:00.123"`
- 解析失败返回 `'格式错误'`，空字符串返回 `'刚刚'`

---

## 二、`lib/config.ts`

```typescript
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || '/api/v1';
```

API 基础路径配置。默认使用相对路径 `/api/v1`，通过 Next.js `rewrites` 代理到后端（`next.config.js` 配置）。

生产环境可通过 `.env.local` 设置 `NEXT_PUBLIC_API_BASE` 直连后端。

---

## 三、`lib/apiError.ts`

### `ApiError` 类

```typescript
class ApiError extends Error {
  code: string;   // 'REQUEST_TIMEOUT' | 'NETWORK_ERROR' | 'UNAUTHORIZED' | 'SERVER_ERROR' | 'INVALID_CONTENT'
  status: number; // HTTP 状态码
}
```

### `notifyLinkDown()`

```typescript
// 调用全局挂载的断链通知函数
(window as any).__setLinkDown?.(true);
```

通过 `window.__setLinkDown` 桥接到 `NetworkContext`，触发 `NeuralLinkAlert` 弹窗。

---

*最后更新：2026-03-11*
