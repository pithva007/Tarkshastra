/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  safelist: ['animate-ping', 'animate-pulse', 'animate-spin'],
  theme: { extend: {} },
  plugins: [],
}
