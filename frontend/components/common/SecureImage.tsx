'use client';

import { useEffect, useState, useRef } from 'react';

interface SecureImageProps {
  src: string;
  alt: string;
  width?: number;
  height?: number;
  className?: string;
  fallback?: React.ReactNode;
}

/**
 * SecureImage — 带鉴权的图片组件
 *
 * 对于指向 /api/v1/public/image 的路径，通过 fetch + Authorization Header 获取
 * 图片二进制数据后转为 Blob URL 渲染，绕过浏览器 <img> 标签无法携带 Header 的限制。
 *
 * 对于外部 http(s):// URL，直接透传给原生 <img>，无需鉴权。
 */
export default function SecureImage({
  src,
  alt,
  width,
  height,
  className,
  fallback,
}: SecureImageProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const prevBlobUrl = useRef<string | null>(null);

  const isSecureProxy =
    src.startsWith('/api/v1/public/image') || src.includes('/api/v1/public/image');

  useEffect(() => {
    // 外部 URL 不走鉴权流程
    if (!isSecureProxy) {
      setBlobUrl(src);
      return;
    }

    let cancelled = false;

    const fetchImage = async () => {
      try {
        const token =
          typeof window !== 'undefined' ? localStorage.getItem('token') : null;

        const res = await fetch(src, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const blob = await res.blob();
        if (cancelled) return;

        const url = URL.createObjectURL(blob);

        // 释放上一个 Blob URL，防止内存泄漏
        if (prevBlobUrl.current) {
          URL.revokeObjectURL(prevBlobUrl.current);
        }
        prevBlobUrl.current = url;
        setBlobUrl(url);
        setError(false);
      } catch {
        if (!cancelled) setError(true);
      }
    };

    fetchImage();

    return () => {
      cancelled = true;
    };
  }, [src, isSecureProxy]);

  // 组件卸载时释放 Blob URL
  useEffect(() => {
    return () => {
      if (prevBlobUrl.current) {
        URL.revokeObjectURL(prevBlobUrl.current);
      }
    };
  }, []);

  if (error) {
    return <>{fallback ?? null}</>;
  }

  if (!blobUrl) {
    // 加载占位
    return (
      <div
        className={className}
        style={{ width, height, background: 'rgba(0,230,246,0.06)' }}
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={blobUrl}
      alt={alt}
      width={width}
      height={height}
      className={className}
    />
  );
}
