/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // Semantic tokens driven by CSS variables (see index.css) — theme-aware.
        surface: {
          DEFAULT: "rgb(var(--surface) / <alpha-value>)",    // main background
          1:       "rgb(var(--surface-1) / <alpha-value>)",  // card / sheet
          2:       "rgb(var(--surface-2) / <alpha-value>)",  // input bg / secondary
          3:       "rgb(var(--surface-3) / <alpha-value>)",  // hover / pressed / separator
        },
        border:     "rgb(var(--border) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)", // primary text
        accent: {
          blue:   "#007AFF",
          green:  "#34C759",
          orange: "#FF9500",
          red:    "#FF3B30",
          purple: "#AF52DE",
        },
        muted:  "rgb(var(--muted) / <alpha-value>)",
        subtle: "rgb(var(--subtle) / <alpha-value>)",
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "Helvetica", "Arial", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card:      "0 1px 3px rgba(0,0,0,0.08)",
        "card-md": "0 2px 8px rgba(0,0,0,0.10)",
        nav:       "0 -1px 0 #E5E5EA",
        "blue-glow": "0 4px 12px rgba(0,122,255,0.35)",
      },
      keyframes: {
        "scan-line": {
          "0%, 100%": { top: "10%" },
          "50%":      { top: "85%" },
        },
      },
      animation: {
        "scan-line": "scan-line 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
