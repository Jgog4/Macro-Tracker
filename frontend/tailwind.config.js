/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Brand palette — "Management Consultant Dark"
        surface: {
          DEFAULT: "#0f1117",
          1:       "#161b27",
          2:       "#1c2333",
          3:       "#232d42",
        },
        border:  "#2a3347",
        accent: {
          green:  "#22c55e",
          blue:   "#3b82f6",
          orange: "#f97316",
          red:    "#ef4444",
          purple: "#a855f7",
        },
        muted:   "#6b7280",
        subtle:  "#9ca3af",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
