import { useState, useEffect } from 'react';
import { getTranslation, type I18nKey } from '@/lib/i18n';

export const LANGUAGE_CHANGED_EVENT = 'languageChanged';

export type Language = 'zh' | 'en';

export function useLanguage() {
  const [lang, setLangState] = useState<Language>('zh');

  useEffect(() => {
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
