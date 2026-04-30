/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // iOS-style light theme — matching the workout tracker app
        surface: {
          DEFAULT: "#F2F2F7",   // main background (light gray)
          1:       "#FFFFFF",   // card / sheet
          2:       "#F2F2F7",   // input bg / secondary
          3:       "#E5E5EA",   // hover / pressed / separator
        },
        border:     "#C6C6C8",
        foreground: "#111827",  // primary text
        accent: {
          blue:   "#007AFF",
          green:  "#34C759",
          orange: "#FF9500",
          red:    "#FF3B30",
          purple: "#AF52DE",
        },
        muted:  "#8E8E93",
        subtle: "#6C6C70",
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
