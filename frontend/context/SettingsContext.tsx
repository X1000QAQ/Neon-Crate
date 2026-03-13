'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { SettingsConfig } from '@/types';

// ── 上下文契约 ────────────────────────────────────────────────────
interface SettingsContextValue {
  /** 当前完整配置（未加载时为 null）*/
  config: SettingsConfig | null;
  /** 是否正在加载 */
  isLoading: boolean;
  /** 是否正在保存 */
  isSaving: boolean;
  /**
   * 更新单个 settings 字段（快捷方法）
   * 仅更新前端内存状态，需调用 saveSettings() 才会持久化到后端
   */
  updateSetting: (key: string, value: string | number | boolean) => void;
  /**
   * 更新 paths 数组（整体替换）
   * 仅更新前端内存状态
   */
  updatePaths: (paths: SettingsConfig['paths']) => void;
  /**
   * 重新从后端拉取最新配置（重置后调用）
   */
  refreshSettings: () => Promise<void>;
  /**
   * 将当前内存中的 config 保存到后端
   * 包含 1+1 路径约束校验
   * 返回 true 表示成功
   */
  saveSettings: (langSetter?: (lang: 'zh' | 'en') => void) => Promise<boolean>;
  /** 直接替换整个 config（供子组件批量更新 paths 使用）*/
  setConfig: (c: SettingsConfig) => void;
}

// ── 创建 Context ──────────────────────────────────────────────────
export const SettingsContext = createContext<SettingsContextValue | null>(null);

// ── Provider ──────────────────────────────────────────────────────
export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [config, setConfigState] = useState<SettingsConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  // 初始加载
  const refreshSettings = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await api.getSettings();
      setConfigState(data);
    } catch (error) {
      // 设置加载失败：静默降级，页面继续渲染（使用空配置兜底），避免白屏
      // 若需用户感知，可在此处接入全局 Toast 系统
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshSettings();
  }, [refreshSettings]);

  // 更新单个 settings 字段
  const updateSetting = useCallback(
    (key: string, value: string | number | boolean) => {
      setConfigState((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          settings: { ...prev.settings, [key]: value },
        };
      });
    },
    []
  );

  // 更新 paths 数组
  const updatePaths = useCallback(
    (paths: SettingsConfig['paths']) => {
      setConfigState((prev) => {
        if (!prev) return prev;
        return { ...prev, paths };
      });
    },
    []
  );

  // 直接替换整个 config
  const setConfig = useCallback((c: SettingsConfig) => {
    setConfigState(c);
  }, []);

  // 保存到后端
  const saveSettings = useCallback(
    async (langSetter?: (lang: 'zh' | 'en') => void): Promise<boolean> => {
      if (!config) return false;

      // 1+1 路径约束校验
      const activeStorage = config.paths.filter(
        (p) => p.enabled && p.type === 'library'
      );
      const movieCount = activeStorage.filter(
        (p) => (p.category || '').toLowerCase() === 'movie'
      ).length;
      const tvCount = activeStorage.filter(
        (p) => (p.category || '').toLowerCase() === 'tv'
      ).length;

      if (movieCount > 1 || tvCount > 1) {
        alert('路径配置冲突：每种类型的媒体库路径最多只能启用一个');
        return false;
      }
      if (activeStorage.length > 0 && (movieCount === 0 || tvCount === 0)) {
        alert('路径配置不完整：已启用媒体库路径，但缺少电影或电视剧分类');
        return false;
      }

      setIsSaving(true);
      try {
        // 先同步前端语言状态
        if (langSetter) {
          langSetter(config.settings.ui_lang as 'zh' | 'en');
        }
        await api.updateSettings(config);
        return true;
      } catch (error) {
        // 设置保存失败：静默降级，返回 false 由调用方决定是否向用户展示错误
        // 调用方（SettingsHub）应在 saveSettings() 返回 false 时给出用户提示
        return false;
      } finally {
        setIsSaving(false);
      }
    },
    [config]
  );

  const contextValue = useMemo(
    () => ({
      config,
      isLoading,
      isSaving,
      updateSetting,
      updatePaths,
      refreshSettings,
      saveSettings,
      setConfig,
    }),
    [config, isLoading, isSaving, updateSetting, updatePaths, refreshSettings, saveSettings, setConfig]
  );

  return (
    <SettingsContext.Provider value={contextValue}>
      {children}
    </SettingsContext.Provider>
  );
}
