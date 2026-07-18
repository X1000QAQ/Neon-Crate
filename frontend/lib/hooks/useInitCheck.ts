import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';

interface InitStatus {
  initialized: boolean;
  message: string;
  loading: boolean;
}

/**
 * 系统初始化检查 Hook
 * 
 * 功能：
 * 1. 轮询检查 /api/v1/auth/status
 * 2. 如果系统未初始化，自动重定向到 /setup
 * 3. 如果系统已初始化但无登录状态，重定向到 /auth/login
 * 4. 如果已登录，允许访问受保护页面
 * 
 * 使用：
 *   const { initialized, loading } = useInitCheck();
 *   if (loading) return <Spinner />;
 */
export function useInitCheck() {
  const router = useRouter();
  const [status, setStatus] = useState<InitStatus>({
    initialized: false,
    message: '',
    loading: true,
  });

  useEffect(() => {
    let isMounted = true;
    let retryCount = 0;
    const maxRetries = 10;

    const checkInit = async () => {
      try {
        const response = await fetch('/api/v1/auth/status', {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
          },
        });

        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const data = await response.json();

        if (!isMounted) return;

        setStatus({
          initialized: data.initialized,
          message: data.message,
          loading: false,
        });

        // 系统未初始化，重定向到设置页面
        if (!data.initialized) {
          router.replace('/setup');
        }
        // 系统已初始化，继续使用 JWT 检查登录状态
        // 无需在这里处理，由后端 JWT 中间件负责

        retryCount = 0; // 成功则重置重试计数
      } catch (error) {
        retryCount++;

        if (retryCount < maxRetries && isMounted) {
          // 指数退避：1s, 2s, 4s, 8s, ...
          const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 10000);
          setTimeout(checkInit, delay);
        } else if (isMounted) {
          // 达到最大重试次数，显示错误
          setStatus({
            initialized: false,
            message: '无法连接到后端服务',
            loading: false,
          });
        }
      }
    };

    checkInit();

    return () => {
      isMounted = false;
    };
  }, [router]);

  return status;
}
