/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        astra: {
          bg: '#0B0F19',
          surface: '#111827',
          'surface-alt': '#1A2236',
          'surface-hover': '#1E293B',
          border: '#1E293B',
          'border-light': '#2A3548',
          accent: '#3B82F6',
          'accent-dim': '#2563EB',
        }
      },
      fontFamily: {
        sans: ['DM Sans', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      }
    },
  },
  plugins: [],
}
