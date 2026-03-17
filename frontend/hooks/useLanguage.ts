import { useState, useEffect } from 'react';
import { getTranslation, type I18nKey } from '@/lib/i18n';

export const LANGUAGE_CHANGED_EVENT = 'languageChanged';

export type Language = 'zh' | 'en';

export function useLanguage() {
  // [P-01 修复 v2] 惰性初始化必须与 SSR 保持一致，始终返回默认值 'zh'。
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
