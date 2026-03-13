import { useContext } from 'react';
import { SettingsContext } from '@/context/SettingsContext';

/**
 * 访问全局配置状态的快捷 Hook
 *
 * 必须在 SettingsProvider 的子树内使用，否则抛出明确错误。
 *
 * 使用示例：
 * ```tsx
 * const { config, updateSetting, refreshSettings } = useSettings();
 * ```
 */
export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) {
    throw new Error(
      '[useSettings] 必须在 <SettingsProvider> 内部使用。' +
      '请检查组件树中是否已挂载 SettingsProvider（通常在 ClientShell 中）。'
    );
  }
  return ctx;
}
