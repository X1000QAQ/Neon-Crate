import { useContext } from 'react';
import { LogContext } from '@/context/LogContext';

/**
 * 访问全局日志状态的快捷 Hook
 *
 * 必须在 LogProvider 的子树内使用，否则抛出明确错误。
 *
 * 使用示例：
 * ```tsx
 * const { logs, isLoading, error } = useLogs();
 * ```
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
