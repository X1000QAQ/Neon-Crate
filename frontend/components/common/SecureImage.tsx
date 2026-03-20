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
 * 路由规则（优先级从高到低）：
 * 1. 占位图 / 空路径 → 原生 <img> 直渲染，绝不走代理（防 403 风暴）
 * 2. http/https 外部链接（TMDB 等）→ 直通，不走鉴权代理
 * 3. 已含 /public/image?path= 的路径 → 直接使用（防重复拼接）
 * 4. 任何物理绝对路径（/ 开头，含 /storage/... 和 /home/...）
 *    → 拼接 API_BASE/public/image?path= 走后端代理引擎（携带 JWT）
 * 5. 其他未知格式 → 原生直通降级兜底
 *
 * 路由补充：凡以 / 开头的本地物理路径（含 /storage、/home 等）一律经 /public/image 代理并携带 JWT，
 * 避免仅匹配单一前缀时旁路绝对路径。
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

    // Rule 1: 占位图 — 原生直渲染，绝不走代理
    if (src === '/placeholder-poster.jpg') {
      setBlobUrl(src);
      return;
    }

    // Rule 2: 外部图片（TMDB 等 http/https）— 直通
    if (src.startsWith('http://') || src.startsWith('https://')) {
      setFinalUrl(src);
      return;
    }

    // Rule 3: 已拼接过代理路径 — 防重复拼接
    if (src.includes('/public/image?path=')) {
      setFinalUrl(src);
      return;
    }

    // Rule 4: 任何物理绝对路径（/storage/... 或 /home/... 等）— 走代理
    if (src.startsWith('/')) {
      setFinalUrl(`${API_BASE}/public/image?path=${encodeURIComponent(src)}`);
      return;
    }

    // Rule 5: 未知格式 — 原生兜底
    setBlobUrl(src);
  }, [src]);

  // Step 2: 用 fetch + Authorization 获取图片，转为 Blob URL
  useEffect(() => {
    if (!finalUrl) return;

    // 外部图片直接渲染（绝对 URL 且不含本站代理路径）
    const isExternalImage =
      (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) &&
      !finalUrl.includes('/public/image?path=');

    if (isExternalImage) {
      setBlobUrl(finalUrl);
      return;
    }

    // 本站代理路径：必须携带 token（AIO 模式下 <img src> 不携带 Authorization 会 401）
    let cancelled = false;

    const fetchImage = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          console.warn('[SecureImage] 无 token，请先登录');
        }

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
