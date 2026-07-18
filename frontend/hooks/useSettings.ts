/**
 * useSettings - 访问全局配置的便捷 Hook
 *
 * 对 `SettingsContext` 的安全封装。相比直接使用 `useContext(SettingsContext)`，
 * 这个 Hook 会在 Provider 缺失时抛出更明确的错误，便于新手定位组件树问题。
 *
 * 使用前提：组件必须位于 `<SettingsProvider>` 子树内。
 */
import { useContext } from 'react';
import { SettingsContext } from '@/context/SettingsContext';

/**
 * useSettings - 全局配置访问 Hook
 * 
 * 核心职责：
 * - 提供快捷方式访问 SettingsContext
 * - 确保在正确的 Provider 子树内使用（否则报错）
 * - 避免手动调用 useContext 时遗漏错误检查
 * 
 * 必须在 SettingsProvider 的子树内使用，否则抛出明确错误提示
 * （通常 SettingsProvider 在 ClientShell 中挂载）
 * 
 * 返回的接口包含：
 * - config: 当前完整配置对象
 * - isLoading: 是否正在加载配置
 * - isSaving: 是否正在保存配置
 * - updateSetting(key, value): 更新单个配置字段（内存操作）
 * - updatePaths(paths): 更新路径配置（内存操作）
 * - saveSettings(): 保存配置到后端
 * - refreshSettings(): 从后端重新加载配置
 * - setConfig(config): 整体替换配置（内存操作）
 * 
 * 使用场景：
 * - SettingsHub 及其所有子 Tab 组件
 * - 任何需要读写系统配置的组件
 * 
 * @example
 * const { config, updateSetting, saveSettings } = useSettings();
 * if (!config) return <Loading />;
 * 
 * updateSetting('ui_lang', 'en');
 * await saveSettings();
 * 
 * @throws 如果在 SettingsProvider 外部使用，抛出错误
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
