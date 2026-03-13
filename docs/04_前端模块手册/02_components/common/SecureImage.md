# SecureImage — 带鉴权的图片组件

**文件路径**: `frontend/components/common/SecureImage.tsx`  
**组件类型**: `'use client'`

---

## 职责

解决浏览器原生 `<img>` 标签无法携带 `Authorization` 请求头的问题。对需要鉴权的本地海报图片，使用 `fetch` + Blob URL 方案绕过限制。

---

## 渲染策略

| 图片类型 | 处理方式 |
|----------|----------|
| `/api/v1/public/image?path=...` | `fetch` + `Authorization: Bearer token` → Blob URL → `<img src={blobUrl}>` |
| `http(s)://` 外部 URL | 直接透传给 `<img src={src}>`，无需鉴权 |

---

## Blob URL 生命周期管理

```typescript
// 释放上一个 Blob URL，防止内存泄漏
if (prevBlobUrl.current) {
  URL.revokeObjectURL(prevBlobUrl.current);
}
prevBlobUrl.current = url;

// 组件卸载时最终释放
useEffect(() => {
  return () => {
    if (prevBlobUrl.current) URL.revokeObjectURL(prevBlobUrl.current);
  };
}, []);
```

---

## Props

| Prop | 类型 | 说明 |
|------|------|------|
| `src` | `string` | 图片地址（代理路径或外部 URL）|
| `alt` | `string` | 图片描述 |
| `width` | `number?` | 宽度 |
| `height` | `number?` | 高度 |
| `className` | `string?` | Tailwind 类名 |
| `fallback` | `ReactNode?` | 加载失败时显示的后备内容 |

---

## 加载状态

| 状态 | 渲染 |
|------|------|
| 加载中（`blobUrl=null`）| 纯色占位块（`rgba(0,230,246,0.06)`）|
| 加载失败（`error=true`）| `fallback` prop 或 `null` |
| 加载成功 | `<img src={blobUrl}>` |

---

## 使用示例

```tsx
<SecureImage
  src={`/api/v1/public/image?path=${encodeURIComponent(localPosterPath)}`}
  alt={task.title}
  width={64}
  height={96}
  className="object-cover w-full h-full"
/>
```
