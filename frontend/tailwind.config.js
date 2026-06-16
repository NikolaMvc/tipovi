/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0A0E14",
        card: "#151B24",
        accent: "#00B3FF",      // neon blue — home / brand / predictions
        draw: "#3A4452",        // grey — draw
        away: "#FF4757",        // red — away / lost
        win: "#00E5A0",         // green — hit tip / HIGH confidence
        amber: "#FFB020",       // pending / MEDIUM confidence
        muted: "#5A6573",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      borderColor: {
        hair: "rgba(255,255,255,0.06)",
      },
      borderRadius: { card: "12px" },
    },
  },
  plugins: [],
};
