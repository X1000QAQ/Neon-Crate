/**
 * ============================================================================
 * AuthGuard - 神经链接认证守卫组件
 * ============================================================================
 *
 * [组件职责]
 * 1. 检查系统初始化状态（首次使用需要初始化）
 * 2. 验证用户 Token（已登录用户才能访问）
 * 3. 显示赛博朋克风格的加载动画（量子凭证同步）
 *
 * [加载逻辑]
 * - 最小展示时间: 1500ms（保留仪式感）
 * - 超时保护: 5000ms（防止卡死）
 * - 退出动画: fade-out + scale-up（平滑过渡）
 *
 * [状态流转]
 * 1. isChecking = true → 显示加载动画
 * 2. 检查完成 + 最小延时 → isChecking = false
 * 3. 退出动画 300ms → 移除组件
 * 4. 渲染主界面
 *
 * authenticatedWrapper：
 * - /auth/login：始终裸渲染 children，不套 wrapper
 * - isAuthenticated：用 wrapper 包裹 children（如注入 SettingsProvider 的壳层）
 * 未认证时不挂载依赖 Token 的全局 Provider，避免登录页周期性 401
 *
 * ============================================================================
 */
'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import { useLanguage } from '@/hooks/useLanguage';

export default function AuthGuard({
  children,
  authenticatedWrapper: Wrapper,
}: {
  children: React.ReactNode;
  /**
   * 可选的已认证页面包装组件（如 AuthenticatedShell）
   * - 传入时：只在 isAuthenticated=true 时将 children 包裹在此组件内
   * - 未传入：直接渲染 children（向后兼容原有用法）
   * - 登录页（/auth/login）：始终跳过此包装，直接渲染裸 children
   */
  authenticatedWrapper?: React.ComponentType<{ children: React.ReactNode }>;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useLanguage();

  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isExiting, setIsExiting] = useState(false);
  const [showBypass, setShowBypass] = useState(false);
  // 1. [计时器登记] -> 2. [卸载清理] -> 3. [卸载后禁写]
  // timerRefs 集中持有 setTimeout id，cleanup 全量 clear，避免卸载后 setState
  const timerRefs = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    return () => { timerRefs.current.forEach(clearTimeout); };
  }, []);

  const checkAuth = useCallback(async () => {
    if (pathname === '/auth/login') {
      setIsChecking(false);
      return;
    }

    const startTime = Date.now();
    let authCheckComplete = false;

    try {
      const status = await api.authStatus();

      if (!status.initialized) {
        router.push('/auth/login');
        return;
      }

      const token = localStorage.getItem('token');
      if (!token) {
        router.push('/auth/login');
        return;
      }

      setIsAuthenticated(true);
      authCheckComplete = true;
    } catch (err) {
      console.error('Auth check failed:', err);
      router.push('/auth/login');
      return;
    }

    // 确保最小展示时间 1500ms（保留赛博朋克仪式感）
    const elapsed = Date.now() - startTime;
    const remainingTime = Math.max(0, 1500 - elapsed);

    timerRefs.current.push(setTimeout(() => {
      if (authCheckComplete) {
        setIsExiting(true);
        timerRefs.current.push(setTimeout(() => {
          setIsChecking(false);
        }, 300));
      }
    }, remainingTime));

    // 超时保护：5秒后显示强制跳过按钮
    timerRefs.current.push(setTimeout(() => {
      setShowBypass(true);
    }, 5000));
  }, [pathname, router]);

  useEffect(() => {
    checkAuth();
  }, [pathname, checkAuth]);

  // 强制跳过加载（用于超时或连接失败）
  const handleBypass = () => {
    setIsExiting(true);
    timerRefs.current.push(setTimeout(() => {
      setIsChecking(false);
      setIsAuthenticated(true);
    }, 300));
  };

  // 登录页：直接渲染裸 children，跳过 authenticatedWrapper
  // 确保 SettingsProvider/LogProvider 不在登录页提前挂载
  if (pathname === '/auth/login') {
    return <>{children}</>;
  }

  // 检查中显示加载状态
  if (isChecking) {
    return (
      <div
        className={`min-h-screen bg-black flex flex-col items-center justify-center relative overflow-hidden transition-all duration-300 ${
          isExiting ? 'opacity-0 scale-105' : 'opacity-100 scale-100'
        }`}
        style={{
          animation: isExiting ? 'none' : 'fade-in 0.5s ease-out'
        }}
      >
        {/* 
          量子加载背景
          - 径向渐变: 顶部青色光晕
          - 网格纹理: 3px 间距，5% 透明度
        */}
        <div className="pointer-events-none absolute inset-0 opacity-40">
          <div className="absolute -inset-32 bg-[radial-gradient(circle_at_top,rgba(0,255,209,0.16),transparent_60%)]" />
          <div className="absolute inset-0 [background-image:linear-gradient(rgba(0,255,209,0.05)_1px,transparent_1px),linear-gradient(90deg,rgba(0,255,209,0.05)_1px,transparent_1px)] [background-size:100%_3px,3px_100%] opacity-40" />
        </div>

        {/* 中央加载器 */}
        <div className="relative flex flex-col items-center gap-6">
          <div className="relative">
            <div className="absolute -inset-6 border border-cyber-cyan/30" />
            <div className="relative flex h-20 w-20 items-center justify-center border border-cyber-cyan/70 bg-black">
              <Loader2 className="h-10 w-10 text-cyber-cyan animate-spin" />
            </div>
          </div>

          {/* 加载文本 */}
          <div className="text-center">
            <p className="font-hacked text-xs sm:text-sm text-cyber-cyan tracking-[0.35em] uppercase">
              {t('auth_initializing')}
              <span className="ml-2 inline-block w-3 h-3 bg-cyber-cyan animate-pulse align-middle" />
            </p>
            <p className="mt-3 font-advent text-xs text-cyber-cyan/70">
              Verifying access channel · Syncing quantum credentials...
            </p>
          </div>

          {/* 超时后显示强制跳过按钮 */}
          {showBypass && (
            <button
              onClick={handleBypass}
              className="mt-8 px-6 py-3 bg-transparent border-2 border-orange-400 text-orange-400 font-semibold uppercase tracking-widest hover:bg-orange-400 hover:text-black transition-all"
              style={{
                boxShadow: '0 0 20px rgba(251, 146, 60, 0.4)',
                animation: 'fade-in 0.5s ease-out'
              }}
            >
              <div className="flex items-center gap-2">
                <AlertTriangle size={18} />
                <span>Force Bypass</span>
              </div>
            </button>
          )}
        </div>
      </div>
    );
  }

  // 已认证：若传入 authenticatedWrapper 则用它包裹 children，否则直接渲染
  // Wrapper（即 AuthenticatedShell）只在此处挂载，登录页绝不触发
  if (isAuthenticated) {
    if (Wrapper) {
      return <Wrapper>{children}</Wrapper>;
    }
    return <>{children}</>;
  }

  // 未认证，不渲染（会被重定向）
  return null;
}
