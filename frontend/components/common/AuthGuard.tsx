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
 * ============================================================================
 */
'use client';

import { useEffect, useState } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { Loader2, AlertTriangle } from 'lucide-react';
import { api } from '@/lib/api';
import { useLanguage } from '@/hooks/useLanguage';

export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { t } = useLanguage();
  
  const [isChecking, setIsChecking] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isExiting, setIsExiting] = useState(false); // 退出动画状态
  const [showBypass, setShowBypass] = useState(false); // 超时后显示强制跳过按钮

  useEffect(() => {
    checkAuth();
  }, [pathname]);

  const checkAuth = async () => {
    // 如果已经在登录页，不需要检查
    if (pathname === '/auth/login') {
      setIsChecking(false);
      return;
    }

    const startTime = Date.now();
    let authCheckComplete = false;

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
      authCheckComplete = true;
    } catch (err) {
      console.error('Auth check failed:', err);
      // 检查失败，跳转登录
      router.push('/auth/login');
      return;
    }

    // 确保最小展示时间 1500ms（保留赛博朋克仪式感）
    const elapsed = Date.now() - startTime;
    const remainingTime = Math.max(0, 1500 - elapsed);

    setTimeout(() => {
      if (authCheckComplete) {
        // 触发退出动画
        setIsExiting(true);
        // 300ms 后完全移除加载界面
        setTimeout(() => {
          setIsChecking(false);
        }, 300);
      }
    }, remainingTime);

    // 超时保护：5秒后显示强制跳过按钮
    setTimeout(() => {
      if (isChecking) {
        setShowBypass(true);
      }
    }, 5000);
  };

  // 强制跳过加载（用于超时或连接失败）
  const handleBypass = () => {
    setIsExiting(true);
    setTimeout(() => {
      setIsChecking(false);
      setIsAuthenticated(true);
    }, 300);
  };

  // 登录页直接渲染
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
          {/* 
            旋转加载图标
            - 外框: 6px 偏移边框
            - 内框: 20x20 容器
            - 图标: 10x10 旋转动画
          */}
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
              className="mt-8 px-6 py-3 bg-transparent border-2 border-orange-400 text-orange-400 font-semibold uppercase tracking-widest hover:bg-orange-400 hover:text-black transition-all animate-pulse"
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

  // 已认证，渲染子组件
  if (isAuthenticated) {
    return <>{children}</>;
  }

  // 未认证，不渲染（会被重定向）
  return null;
}
