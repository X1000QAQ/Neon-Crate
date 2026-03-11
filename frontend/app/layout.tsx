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
