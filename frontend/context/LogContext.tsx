'use client';

import React, { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { LogEntry } from '@/types';

const POLL_INTERVAL_MS = 1500; // 1.5秒轮询间隔，提升数据流感
const MAX_LOG_LINES = 200;      // 全量上限，防止内存无限增长

interface LogContextValue {
  /** 全量原始日志（最近 MAX_LOG_LINES 条）*/
  logs: LogEntry[];
  /** 首次加载状态（仅在 logs 为空时为 true，后续轮询不触发此状态）*/
  isInitialLoading: boolean;
  /** 上次请求错误信息 */
  error: string | null;
  /** 手动立即拉取一次（供手动刷新使用）*/
  fetchNow: () => void;
}

export const LogContext = createContext<LogContextValue | null>(null);

export function LogProvider({ children }: { children: React.ReactNode }) {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  // isInitialLoading：仅在 logs 为空时为 true，后续轮询静默更新，不触发黑屏加载
  const [isInitialLoading, setIsInitialLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchLogs = useCallback(async () => {
    try {
      // 无 tags 参数，拉取全量，让各消费组件自行前端过滤
      const list = await api.getSystemLogs();
      setLogs((list || []).slice(-MAX_LOG_LINES));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      // 首次请求完成后关闭初始加载状态，后续轮询不再修改此值
      setIsInitialLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchLogs();

    // 页面可见性优化：切换 Tab 时暂停轮询，节省性能
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        void fetchLogs();
      }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  }, [fetchLogs]);

  const contextValue = useMemo(
    () => ({ logs, isInitialLoading, error, fetchNow: fetchLogs }),
    [logs, isInitialLoading, error, fetchLogs]
  );

  return (
    <LogContext.Provider value={contextValue}>
      {children}
    </LogContext.Provider>
  );
}
