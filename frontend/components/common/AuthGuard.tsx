'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { api } from '@/lib/api';
import { useLanguage } from '@/hooks/useLanguage';

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useLanguage();
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    checkAuth();
  }, [pathname]);

  const checkAuth = async () => {
    // 如果已经在登录页，不需要检查
    if (pathname === '/auth/login') {
      setIsChecking(false);
      return;
    }

    try {
      // 检查系统是否已初始化
      const status = await api.authStatus();

      if (!status.initialized) {
        // 系统未初始化，跳转到登录页进行初始化
        router.push('/auth/login');
        return;
      }

      // 检查是否有 Token
      const token = localStorage.getItem('token');
      if (!token) {
        // 无 Token，跳转登录
        router.push('/auth/login');
        return;
      }

      // Token 存在，允许访问
      setIsAuthenticated(true);
    } catch (err) {
      console.error('Auth check failed:', err);
      // 检查失败，跳转登录
      router.push('/auth/login');
    } finally {
      setIsChecking(false);
    }
  };

  // 登录页直接渲染
  if (pathname === '/auth/login') {
    return <>{children}</>;
  }

  // 检查中显示加载状态
  if (isChecking) {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center relative overflow-hidden">
        {/* Quantum loading background */}
        <div className="pointer-events-none absolute inset-0 opacity-40">
          <div className="absolute -inset-32 bg-[radial-gradient(circle_at_top,rgba(0,255,209,0.16),transparent_60%)]" />
          <div className="absolute inset-0 [background-image:linear-gradient(rgba(0,255,209,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,209,0.05)_1px,transparent_1px)] [background-size:100%_3px,3px_100%] opacity-40" />
        </div>

        <div className="relative flex flex-col items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-6 border border-cyber-cyan/30" />
            <div className="relative flex h-20 w-20 items-center justify-center border border-cyber-cyan/70 bg-black">
              <Loader2 className="h-10 w-10 text-cyber-cyan animate-spin" />
            </div>
          </div>

          <div className="text-center">
            <p className="font-hacked text-xs sm:text-sm text-cyber-cyan tracking-[0.35em] uppercase">
              {t('auth_initializing')}
              <span className="ml-2 inline-block w-3 h-3 bg-cyber-cyan animate-pulse align-middle" />
            </p>
            <p className="mt-3 font-advent text-xs text-cyber-cyan/70">
              Verifying access channel · Syncing quantum credentials...
            </p>
          </div>
        </div>
      </div>
    );
  }

  // 已认证，渲染子组件
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // 未认证，不渲染（会被重定向）
  return null;
}
