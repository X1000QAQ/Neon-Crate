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
