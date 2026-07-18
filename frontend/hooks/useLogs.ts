/**
 * useLogs - 访问全局日志的便捷 Hook
 *
 * 对 `LogContext` 的安全封装。用于读取全局日志缓存、首次加载状态、错误信息，
 * 以及手动刷新日志的 `fetchNow()` 方法。
 *
 * 使用前提：组件必须位于 `<LogProvider>` 子树内。
 */
import { useContext } from 'react';
import { LogContext } from '@/context/LogContext';

/**
 * useLogs - 全局日志访问 Hook
 * 
 * 核心职责：
 * - 提供快捷方式访问 LogContext
 * - 确保在正确的 Provider 子树内使用（否则报错）
 * - 避免手动调用 useContext 时遗漏错误检查
 * 
 * 必须在 LogProvider 的子树内使用，否则抛出明确错误提示
 * （通常 LogProvider 在 ClientShell 中挂载）
 * 
 * 返回的接口包含：
 * - logs: 日志条目数组（最多 200 条）
 * - isInitialLoading: 首次加载状态
 * - error: 上次请求的错误信息
 * - fetchNow(): 手动立即刷新日志
 * 
 * 使用场景：
 * - SystemMonitor 组件实时显示系统日志
 * - MiniLog 组件显示最近日志
 * - 任何需要监听系统运行状态的组件
 * 
 * @example
 * const { logs, isInitialLoading, error, fetchNow } = useLogs();
 * if (isInitialLoading) return <Loading />;
 * return <LogList logs={logs} />;
 * 
 * @throws 如果在 LogProvider 外部使用，抛出错误
 */
export function useLogs() {
  const ctx = useContext(LogContext);
  if (!ctx) {
    throw new Error(
      '[useLogs] 必须在 <LogProvider> 内部使用。' +
      '请检查组件树中是否已挂载 LogProvider（通常在 ClientShell 中）。'
    );
  }
  return ctx;
}
