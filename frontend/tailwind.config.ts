import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: '#0d1117',
          secondary: '#1a1a2e',
          elevated: '#1e2130',
          border: '#2a2d3a',
        },
        accent: {
          yellow: '#ecad0a',
          blue: '#209dd7',
          purple: '#753991',
        },
        price: {
          up: '#22c55e',
          down: '#ef4444',
          flat: '#6b7280',
        },
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      keyframes: {
        'flash-up': {
          '0%': { backgroundColor: 'rgba(34, 197, 94, 0.4)' },
          '100%': { backgroundColor: 'transparent' },
        },
        'flash-down': {
          '0%': { backgroundColor: 'rgba(239, 68, 68, 0.4)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
      animation: {
        'flash-up': 'flash-up 500ms ease-out forwards',
        'flash-down': 'flash-down 500ms ease-out forwards',
      },
    },
  },
  plugins: [],
}

export default config
