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
        // Scoped to the public homepage only (Landing.jsx + the header's
        // `dark` variant, which only Landing uses) -- matches the
        // indigo-violet from the ROSKYRO logo mark. The rest of the app
        // (dashboard, sidebar, every other page) keeps the `brand` green
        // above untouched, by request.
        landing: {
          50: '#f4f1fb',
          100: '#e7e0f7',
          200: '#cec0f2',
          300: '#a990ea',
          400: '#7950e2',
          500: '#4e18d8',
          600: '#3d0fb3',
          700: '#330e90',
          800: '#2b116f',
          900: '#241155',
          950: '#160c32',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
