/**
 * LogContext - 全局系统日志状态容器
 *
 * 负责定时从后端拉取系统日志，并把最新日志提供给 `SystemMonitor`、`MiniLog`
 * 等展示组件。轮询逻辑集中在这里，可以避免多个组件各自请求后端，减少重复流量。
 *
 * 新手提示：
 * - `logs` 是最近的日志缓存，不建议在组件内再次请求日志接口。
 * - `isInitialLoading` 只代表首次加载，后续轮询不会反复触发加载态。
 * - 如需手动刷新，调用 `fetchNow()` 即可。
 */
'use client';

import React, { createContext, useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { LogEntry } from '@/types';

/**
 * LogContext - 系统日志实时轮询上下文
 * 
 * 核心职责：
 * - 从后端定期轮询获取最新日志
 * - 维护本地日志缓冲（最多 200 条）
 * - 管理首次加载状态和错误信息
 * - 支持手动立即刷新
 * 
 * 轮询策略：
 * - 初始化时立即拉取一次日志
 * - 之后每 5 秒自动轮询一次
 * - 页面失焦时暂停轮询（节省性能）
 * - 首次加载和后续轮询分离状态（避免 UI 闪烁）
 * 
 * 使用场景：
 * - SystemMonitor 组件实时显示系统运行日志
 * - 用户可以按标签过滤日志
 */

const POLL_INTERVAL_MS = 5000;  // 轮询间隔 5 秒
const MAX_LOG_LINES = 200;      // 最多保留 200 条日志，防止内存无限增长

interface LogContextValue {
  /** 全量日志条目数组（最多 MAX_LOG_LINES 条，按时间倒序） */
  logs: LogEntry[];
  
  /**
   * 首次加载状态
   * - 页面首次渲染，正在加载日志时为 true
   * - 首次加载完成后始终为 false
   * - 后续的定时轮询不会影响此状态（避免 UI 频繁闪烁）
   */
  isInitialLoading: boolean;
  
  /** 上次请求失败时的错误信息，成功时为 null */
  error: string | null;
  
  /** 手动触发一次立即刷新（用于用户主动点击"刷新"按钮） */
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
