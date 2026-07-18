/**
 * SettingsContext - 全局配置状态容器
 *
 * 负责从后端加载系统配置，并向设置页各个 Tab 提供统一的读写入口。
 * 这里的修改采用“先写入前端内存，再由用户点击保存持久化”的模式，
 * 避免每个输入框变化都立即请求后端。
 *
 * 新手提示：
 * - `updateSetting()` 只更新内存，不会保存到数据库。
 * - `saveSettings()` 才会把当前配置提交给后端。
 * - 组件必须位于 `<SettingsProvider>` 子树内，才能通过 `useSettings()` 访问配置。
 */
'use client';

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import type { SettingsConfig } from '@/types';

/**
 * SettingsContext - 全局配置管理上下文
 * 
 * 核心职责：
 * - 持有完整的系统配置对象（settings + paths）
 * - 提供配置的读取、修改、保存接口
 * - 管理加载和保存状态
 * - 与后端同步配置的生命周期
 * 
 * 架构特点：
 * - 本地状态缓冲：修改时仅更新前端内存，不立即后端同步
 * - 显式提交：需要调用 saveSettings() 才会持久化
 * - 批量操作：支持单个字段更新和整体替换
 * 
 * 使用场景：
 * - SettingsHub 中的所有 Tab 组件共享同一份配置
 * - 提供统一的配置读写入口，避免数据不一致
 */
interface SettingsContextValue {
  /** 当前完整配置对象（包含 settings 和 paths），未加载时为 null */
  config: SettingsConfig | null;
  
  /** 是否正在从后端加载配置 */
  isLoading: boolean;
  
  /** 是否正在向后端保存配置 */
  isSaving: boolean;
  
  /**
   * 更新单个配置字段（内存操作，不会立即保存到后端）
   * 
   * @param key - 配置字段名（如 'ui_lang', 'min_size_mb'）
   * @param value - 新的字段值
   * 
   * @example
   * updateSetting('ui_lang', 'en');
   * updateSetting('min_size_mb', 50);
   */
  updateSetting: (key: string, value: string | number | boolean) => void;
  
  /**
   * 整体替换 paths 数组（内存操作，不会立即保存到后端）
   * 
   * @param paths - 新的路径配置数组
   * 
   * @example
   * updatePaths([
   *   { type: 'storage', path: '/media/movies', category: 'Movie', enabled: true },
   *   { type: 'storage', path: '/media/tv', category: 'TV', enabled: true }
   * ]);
   */
  updatePaths: (paths: SettingsConfig['paths']) => void;
  
  /**
   * 从后端重新加载最新配置（通常在重置后调用）
   */
  refreshSettings: () => Promise<void>;
  
  /**
   * 将内存中的配置保存到后端
   * 
   * @param langSetter - 可选的语言切换回调（若后端返回新的语言设置）
   * @returns true 表示保存成功，false 表示保存失败
   * 
   * 工作流程：
   * 1. 设置 isSaving = true
   * 2. 调用 api.updateSettings(config)
   * 3. 若成功则返回 true；若失败则返回 false
   * 4. 设置 isSaving = false
   * 
   * 注意：错误处理由调用方负责（通过 Toast 等方式展示错误信息）
   */
  saveSettings: (langSetter?: (lang: 'zh' | 'en') => void) => Promise<boolean>;
  
  /**
   * 直接替换整个配置对象（内存操作，不会立即保存到后端）
   * 供子组件执行批量更新时使用
   */
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

  // 保存到后端（所有路径约束校验由后端执行）
  const saveSettings = useCallback(
    async (langSetter?: (lang: 'zh' | 'en') => void): Promise<boolean> => {
      if (!config) return false;

      setIsSaving(true);
      try {
        // 同步前端语言状态
        if (langSetter) {
          langSetter(config.settings.ui_lang as 'zh' | 'en');
        }
        // 后端作为唯一的权威校验层，处理所有路径约束逻辑
        await api.updateSettings(config);
        return true;
      } catch (error) {
        // 后端返回错误时，由调用方（SettingsHub）展示错误信息
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
