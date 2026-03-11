# Context 与 Hooks - `context/` + `hooks/`

---

## 一、`context/NetworkContext.tsx`

全局网络状态管理，检测后端连接是否断开。

### `NetworkProvider`

```typescript
<NetworkProvider>{children}</NetworkProvider>
```

在 `ClientShell` 最外层包裹，所有子组件可通过 `useNetwork()` 消费。

### `useNetwork() -> { isLinkDown, setLinkDown }`

读取断链状态的 Hook。

### `window.__setLinkDown` 桥接

```typescript
// NetworkProvider 挂载时注册
(window as any).__setLinkDown = setIsLinkDown;

// api.ts 中调用
(window as any).__setLinkDown?.(true);  // 触发断链弹窗
```

这是一个「全局命令式触发」模式：`api.ts` 是普通模块（不是 React 组件），无法直接用 Context，通过 `window` 桥接实现跨层通信。

**组件卸载时自动清理：**
```typescript
return () => { delete (window as any).__setLinkDown; }
```

---

## 二、`hooks/useLanguage.ts`

语言状态管理 Hook。

```typescript
const { lang, setLang, t } = useLanguage();
```

| 返回值 | 说明 |
|---|---|
| `lang` | 当前语言（`'zh'` \| `'en'`）|
| `setLang(lang)` | 切换语言，写入 `localStorage` 并 dispatch `languageChanged` 事件 |
| `t(key)` | 翻译函数，返回当前语言对应文本 |

**跨组件同步机制：**

```
setLang() → localStorage.setItem('ui_lang', lang)
          → dispatchEvent(new CustomEvent('languageChanged'))

其他组件中的 useLanguage()
  → addEventListener('languageChanged', handler)
  → handler 读取 localStorage 更新状态
  → 组件重新渲染
```

**初始化：** `useEffect` 从 `localStorage.ui_lang` 恢复语言设置。

---

*最后更新：2026-03-11*
