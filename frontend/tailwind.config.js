/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./public/index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff9f6',
          100: '#d7f0e7',
          200: '#b0e1d0',
          300: '#7fccb2',
          400: '#4fb090',
          500: '#2f9576',
          600: '#20785f',
          700: '#1c604d',
          800: '#1a4d40',
          900: '#174036',
          950: '#0a241f',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
