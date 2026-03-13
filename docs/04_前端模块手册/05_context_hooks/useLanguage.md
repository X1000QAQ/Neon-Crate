# useLanguage — 多语言 Hook

**文件路径**: `frontend/hooks/useLanguage.ts`

---

## 职责

提供多语言状态管理和翻译函数，支持运行时切换语言而无需刷新页面（除 SettingsHub 保存后主动刷新外）。

---

## 返回值

```typescript
const { lang, setLang, t } = useLanguage();

lang    // 当前语言: 'zh' | 'en'
setLang // 切换语言函数
t       // 翻译函数: (key: I18nKey) => string
```

---

## 初始化流程

```typescript
// 1. useState 默认 'zh'
// 2. useEffect 从 localStorage 读取持久化语言
const saved = localStorage.getItem('ui_lang');
if (saved === 'zh' || saved === 'en') setLangState(saved);
```

---

## setLang 流程

```typescript
const setLang = (newLang: Language) => {
  setLangState(newLang);                              // 更新本地状态
  localStorage.setItem('ui_lang', newLang);           // 持久化
  window.dispatchEvent(new CustomEvent('languageChanged')); // 广播事件
};
```

所有挂载中的 `useLanguage` 实例监听 `languageChanged` 事件，收到后重新读取 localStorage，实现跨组件同步。

---

## 语言事件常量

```typescript
export const LANGUAGE_CHANGED_EVENT = 'languageChanged';
```

---

## 与 SettingsHub 的关系

`SettingsHub.handleSave()` 在保存设置时调用 `setLang(config.settings.ui_lang)`，之后再调用 `window.location.reload()`，确保保存后全面刷新使所有字典 Key 重新加载。
