# tailwind.config.ts — Tailwind 扩展配置

**文件路径**: `frontend/tailwind.config.ts`

---

## 扩展字体

```typescript
fontFamily: {
  'advent': ['Advent Pro', 'Orbitron', 'Segoe UI', 'sans-serif'],
  'hacked': ['Hacked', 'monospace'],
}
```

使用方式：
```html
<h1 class="font-advent">标题</h1>
<input class="font-hacked" />
```

---

## 扩展颜色

```typescript
colors: {
  'cyber-cyan':   'rgba(var(--cyber-cyan-rgb), <alpha-value>)',
  'cyber-yellow': 'rgba(var(--cyber-yellow-rgb), <alpha-value>)',
  'cyber-red':    'rgba(var(--cyber-red-rgb), <alpha-value>)',
  'cyber-bg':     '#000000',
  'cyber-border': '#8ae66e',
}
```

支持 Tailwind 透明度修饰符：
```html
<div class="bg-cyber-cyan/10 border-cyber-cyan/50 text-cyber-red">
```

对应 CSS：
```css
background: rgba(0, 230, 246, 0.1);
border-color: rgba(0, 230, 246, 0.5);
color: rgba(255, 1, 60, 1);
```

---

## content 扫描路径

```typescript
content: [
  './pages/**/*.{js,ts,jsx,tsx,mdx}',
  './components/**/*.{js,ts,jsx,tsx,mdx}',
  './app/**/*.{js,ts,jsx,tsx,mdx}',
]
```

覆盖 Next.js App Router 所有组件路径，确保按需生成 CSS 类。

---

## 常用类速查

| Tailwind 类 | 实际颜色 |
|-------------|----------|
| `text-cyber-cyan` | `#00e6f6` |
| `text-cyber-yellow` | `#f9f002` |
| `text-cyber-red` | `#ff013c` |
| `border-cyber-cyan/30` | `rgba(0,230,246,0.3)` |
| `bg-cyber-cyan/10` | `rgba(0,230,246,0.1)` |
| `font-advent` | Advent Pro |
| `font-hacked` | Hacked |
