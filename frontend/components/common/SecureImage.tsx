'use client';

import { useEffect, useState, useRef } from 'react';
import { API_BASE } from '@/lib/config';

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
 * 双模式自适应：
 * - 开发模式（3000+8000）：API_BASE = 'http://localhost:8000/api/v1'（绝对路径）
 *   → fetch + Authorization header → Blob URL 渲染
 * - AIO 生产模式（单端口 8000）：API_BASE = '/api/v1'（相对路径）
 *   → 同样走 fetch + Authorization header → Blob URL 渲染
 *   → ⚠️ 不能用 <img src> 直接渲染，因为图片代理路由有 JWT 鉴权
 *
 * 核心约束：
 * - 上游（MediaTable.getPosterUrl）必须传入原始物理路径，严禁提前拼接 /api/v1/public/image?path=
 * - 外部链接（TMDB 等 http/https）直通，不做鉴权处理
 */
export default function SecureImage({
  src,
  alt,
  width,
  height,
  className,
  fallback,
}: SecureImageProps) {
  const [finalUrl, setFinalUrl] = useState<string>('');
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const prevBlobUrl = useRef<string | null>(null);

  // Step 1: 计算最终请求 URL
  useEffect(() => {
    if (!src) return;

    // 外部图片（TMDB 等）直通，不走鉴权代理
    if (src.startsWith('http')) {
      setFinalUrl(src);
      return;
    }

    // 本地物理路径 → 拼接后端代理地址
    // API_BASE 在开发模式为绝对路径，AIO 模式为相对路径，两种情况都需要 fetch+token
    const targetPath = src.includes('/public/image?path=')
      ? src
      : `${API_BASE}/public/image?path=${encodeURIComponent(src)}`;

    setFinalUrl(targetPath);
    console.warn('🚀 [SecureImage] 目标地址:', targetPath);
  }, [src]);

  // Step 2: 用 fetch + Authorization 获取图片，转为 Blob URL
  useEffect(() => {
    if (!finalUrl) return;

    // 外部图片（已在 Step 1 判断为 http 开头的绝对 URL 且非本站）直接渲染
    // 判断条件：绝对 URL 且不包含 /public/image（即不是本站代理路径）
    const isExternalImage =
      (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) &&
      !finalUrl.includes('/public/image?path=');

    if (isExternalImage) {
      setBlobUrl(finalUrl);
      return;
    }

    // 本站图片代理（无论相对路径还是绝对路径）：必须携带 token
    // AIO 模式下 <img src> 标签不携带 Authorization，直接渲染会 401
    let cancelled = false;

    const fetchImage = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          console.warn('🔑 [SecureImage] 无 token，请先登录');
        }

        // 相对路径需补全为绝对 URL 才能 fetch（浏览器 fetch 支持相对路径，无需处理）
        const res = await fetch(finalUrl, {
          headers: { Authorization: `Bearer ${token ?? ''}` },
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        const blob = await res.blob();
        if (cancelled) return;

        const url = URL.createObjectURL(blob);
        if (prevBlobUrl.current) URL.revokeObjectURL(prevBlobUrl.current);
        prevBlobUrl.current = url;
        setBlobUrl(url);
        setError(false);
      } catch {
        if (!cancelled) setError(true);
      }
    };

    fetchImage();
    return () => { cancelled = true; };
  }, [finalUrl]);

  // 卸载时释放 Blob URL，防止内存泄漏
  useEffect(() => {
    return () => {
      if (prevBlobUrl.current) URL.revokeObjectURL(prevBlobUrl.current);
    };
  }, []);

  if (error) return <>{fallback ?? null}</>;

  if (!blobUrl) {
    return (
      <div
        className={className}
        style={{ width, height, background: 'rgba(0,230,246,0.06)' }}
      />
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={blobUrl} alt={alt} width={width} height={height} className={className} />
  );
}
