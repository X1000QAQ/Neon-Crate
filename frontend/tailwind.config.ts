/**
 * tailwind.config - Tailwind CSS 主题配置
 *
 * 定义前端项目使用的字体、扫描路径和赛博朋克主题色。
 * 颜色主要引用 `globals.css` 中的 CSS 变量，保证主题色在 Tailwind 类和原生 CSS 中保持一致。
 *
 * 新手提示：
 * - 新增组件目录时，需要确认 `content` 数组能扫描到对应文件。
 * - 主题色不要在组件中随意硬编码，优先使用这里定义的 `cyber-*` 颜色。
 */
import type { Config } from 'tailwindcss';

/**
 * Tailwind 配置（v1.0.0）
 *
 * 美学口径：
 * - Holographic Void（全息虚空）为默认视觉域：霓虹青为主，黄/红仅用于强调与告警。
 * - 色值统一走 `globals.css` 的 CSS 变量，避免离散硬编码色。
 */
const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        'advent': ['Advent Pro', 'Orbitron', 'Segoe UI', 'sans-serif'],
        'hacked': ['Hacked', 'monospace'],
      },
      colors: {
        'cyber-cyan':   'rgba(var(--cyber-cyan-rgb), <alpha-value>)',
        'cyber-yellow': 'rgba(var(--cyber-yellow-rgb), <alpha-value>)',
        'cyber-red':    'rgba(var(--cyber-red-rgb), <alpha-value>)',
        'cyber-bg':     '#000000',
        'cyber-border': '#8ae66e',
      },
    },
  },
  plugins: [],
};

export default config;
