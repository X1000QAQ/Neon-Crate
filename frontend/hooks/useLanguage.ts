/**
 * useLanguage - 多语言管理 Hook
 * 
 * 核心职责：
 * - 管理当前 UI 语言状态（中文 / 英文）
 * - 同步用户语言偏好到 localStorage
 * - 监听全局语言切换事件
 * - 提供翻译函数 t() 获取本地化字符串
 * 
 * 实现细节：
 * - 使用惰性初始化避免 SSR Hydration 不匹配错误
 * - localStorage 读取延迟到 useEffect（Hydration 完成后）
 * - 语言切换时自动广播 CustomEvent，其他 Tab 页面可同步感知
 * 
 * 使用场景：
 * - 所有需要多语言支持的组件都应调用此 Hook
 * - 语言切换通常由 LanguageSelector 组件触发
 * 
 * @example
 * const { lang, setLang, t } = useLanguage();
 * console.log(lang);  // 'zh' | 'en'
 * t('dashboard_btn_scan');  // 获取翻译文本
 * setLang('en');  // 切换语言
 */

import { useState, useEffect } from 'react';
import { getTranslation, type I18nKey } from '@/lib/i18n';

export const LANGUAGE_CHANGED_EVENT = 'languageChanged';

export type Language = 'zh' | 'en';

export function useLanguage() {
  /**
   * 语言状态：惰性初始化
   * - 初始值为 'zh'（默认中文）
   * - 首屏 SSR 输出与客户端一致，避免 Hydration mismatch
   * - 真实的 localStorage 值在 useEffect 中同步
   */
  const [lang, setLangState] = useState<Language>('zh');

  /**
   * 第一个 useEffect：初始化阶段
   * 在 Hydration 完成后，从 localStorage 读取用户上次选择的语言
   * 仅执行一次（空依赖数组）
   */
  useEffect(() => {
    const saved = localStorage.getItem('ui_lang');
    if (saved === 'zh' || saved === 'en') {
      setLangState(saved);
    }
  }, []);

  /**
   * 第二个 useEffect：事件监听
   * 监听 LANGUAGE_CHANGED_EVENT 事件，当其他 Tab 页面切换语言时同步感知
   * 这样可以实现多 Tab 语言一致性
   */
  useEffect(() => {
    const handleLanguageChange = () => {
      const newLang = localStorage.getItem('ui_lang');
      if (newLang === 'zh' || newLang === 'en') {
        setLangState(newLang);
      }
    };

    window.addEventListener(LANGUAGE_CHANGED_EVENT, handleLanguageChange);

    return () => {
      window.removeEventListener(LANGUAGE_CHANGED_EVENT, handleLanguageChange);
    };
  }, []);

  /**
   * 切换语言
   * 
   * 流程：
   * 1. 更新本地状态
   * 2. 保存到 localStorage（持久化）
   * 3. 广播 CustomEvent（供其他 Tab 同步）
   * 
   * @param newLang - 新语言（'zh' 或 'en'）
   */
  const setLang = (newLang: Language) => {
    setLangState(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('ui_lang', newLang);
      window.dispatchEvent(new CustomEvent(LANGUAGE_CHANGED_EVENT));
    }
  };

  /**
   * 翻译函数
   * 
   * @param key - 翻译键（如 'dashboard_btn_scan'）
   * @param fallback - 可选的回退文本（若键不存在时使用）
   * @returns 本地化文本
   * 
   * @example
   * t('dashboard_btn_scan')  // 返回 '扫描' 或 'Scan'
   * t('custom_key', 'Default Text')  // 键不存在时返回 'Default Text'
   */
  const t = (key: string, fallback?: string): string => {
    if (fallback !== undefined) {
      return getTranslation(lang, key, fallback);
    }
    return getTranslation(lang, key as I18nKey);
  };

  return { lang, setLang, t };
}
