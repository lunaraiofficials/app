/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: [
    './pages/**/*.{js,jsx}',
    './components/**/*.{js,jsx}',
    './app/**/*.{js,jsx}',
    './src/**/*.{js,jsx}',
  ],
  prefix: "",
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      fontFamily: {
        heading: ['Outfit', 'sans-serif'],
        body: ['DM Sans', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        border: "#E7E5E4",
        input: "#E7E5E4",
        ring: "#064E3B",
        background: "#FAFAF9",
        foreground: "#1C1917",
        primary: {
          DEFAULT: "#064E3B",
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#FAFAF9",
          foreground: "#1C1917",
        },
        accent: {
          DEFAULT: "#D9F99D",
          foreground: "#365314",
        },
        muted: {
          DEFAULT: "#F5F5F4",
          foreground: "#57534E",
        },
        destructive: {
          DEFAULT: "#EF4444",
          foreground: "#FFFFFF",
        },
        card: {
          DEFAULT: "#FFFFFF",
          foreground: "#1C1917",
        },
        popover: {
          DEFAULT: "#FFFFFF",
          foreground: "#1C1917",
        },
      },
      borderRadius: {
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.125rem",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}