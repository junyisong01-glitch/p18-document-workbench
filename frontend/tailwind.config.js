/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#18233A',
          muted: '#526077',
          subtle: '#7B8798',
        },
        line: {
          DEFAULT: '#E1E9F6',
          soft: '#EEF3FA',
        },
      },
      fontFamily: {
        sans: ['"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei"', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(37, 99, 235, 0.04), 0 10px 28px rgba(37, 99, 235, 0.07)',
        dialog: '0 24px 60px rgba(24, 35, 58, 0.18)',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'dialog-in': {
          from: { opacity: '0', transform: 'translateY(8px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'drawer-in': {
          from: { opacity: '0', transform: 'translateX(24px)' },
          to: { opacity: '1', transform: 'translateX(0)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 180ms ease-out',
        'dialog-in': 'dialog-in 220ms cubic-bezier(0.16, 1, 0.3, 1)',
        'drawer-in': 'drawer-in 260ms cubic-bezier(0.16, 1, 0.3, 1)',
      },
    },
  },
  plugins: [],
};
