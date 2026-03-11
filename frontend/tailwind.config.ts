import type { Config } from 'tailwindcss';

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
