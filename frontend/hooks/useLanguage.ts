import { useState, useEffect } from 'react';
import { getTranslation, type I18nKey } from '@/lib/i18n';

export const LANGUAGE_CHANGED_EVENT = 'languageChanged';

export type Language = 'zh' | 'en';

export function useLanguage() {
  // 语言状态：惰性初始化与 SSR 首屏一致，缺省为 zh，避免水合漂移
  // 客户端 localStorage 同步移至 useEffect，确保 Hydration 完成后再切换语言，
  // 彻底消除 Server/Client 文本不匹配的 Hydration Error。
  const [lang, setLangState] = useState<Language>('zh');

  useEffect(() => {
    // Hydration 完成后，从 localStorage 读取用户语言偏好并同步
    const saved = localStorage.getItem('ui_lang');
    if (saved === 'zh' || saved === 'en') {
      setLangState(saved);
    }
  }, []);

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

  const setLang = (newLang: Language) => {
    setLangState(newLang);
    if (typeof window !== 'undefined') {
      localStorage.setItem('ui_lang', newLang);
      window.dispatchEvent(new CustomEvent(LANGUAGE_CHANGED_EVENT));
    }
  };

  const t = (key: I18nKey): string => {
    return getTranslation(lang, key);
  };

  return { lang, setLang, t };
}
