import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ivory: "#F0EEE6",
        paper: "#FAF9F5",
        manila: "#E8DCC4",
        espresso: "#191919",
        sand: "#D4CDB8",
        stone: "#8C8578",
        coral: { DEFAULT: "#CC785C", deep: "#B35A3E", soft: "#E8B5A0" },
        good: "#3F7D58",
        bad: "#B23A48",
      },
      fontFamily: {
        display: ["'Archivo Black'", "system-ui", "sans-serif"],
        body: ["Inter", "system-ui", "sans-serif"],
        serif: ["'Instrument Serif'", "Georgia", "serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      letterSpacing: { tightest: "-0.04em", display: "-0.025em" },
    },
  },
  plugins: [],
} satisfies Config;
