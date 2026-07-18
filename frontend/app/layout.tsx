/**
 * RootLayout - Next.js 全局根布局
 *
 * 负责挂载全局样式、页面元信息，以及包裹所有页面的 `ClientShell`。
 * 该文件保持为 Server Component，不使用 `'use client'`，客户端状态统一下沉到子组件处理。
 *
 * 新手提示：
 * - 全局 Provider、错误边界和鉴权壳层都在 `ClientShell` 中组织。
 * - `<html lang>` 固定为 `zh-CN`，避免服务端和客户端语言状态不一致导致 Hydration 警告。
 * - 页面级内容通过 `{children}` 注入。
 */
import "./globals.css";
import ClientShell from '@/components/common/ClientShell';

// layout.tsx must be a Server Component (no 'use client').
// Dynamic lang logic lives inside child components via useLanguage().
// Keeping <html lang> static avoids SSR/client hydration mismatch.

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <head>
        <title>Neon Crate - 数据容器编排引擎</title>
        <meta name="description" content="Digital Container Engine for structured data orchestration" />
      </head>
      <body>
        <ClientShell>{children}</ClientShell>
      </body>
    </html>
  );
}
