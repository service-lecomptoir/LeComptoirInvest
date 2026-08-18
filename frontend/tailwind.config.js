/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      // Same brand tokens as the sibling products, on purpose: a fund console that
      // looked like a different company would make the family read as three vendors.
      colors: {
        brand: {
          navy: '#0D2F5C',
          'navy-light': '#1A4A8A',
          teal: '#0E9F8E',
          orange: '#F07800',
        },
      },
    },
  },
  plugins: [],
}
