/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Light theme — warm Claude.ai-inspired palette.
        bg:        "#FAF9F6",   // app background (warm off-white)
        panel:     "#FFFFFF",   // composer, cards
        sidebar:   "#F2F0EA",   // left sidebar
        elevated:  "#F7F5F0",   // assistant bubble fill
        userBubble:"#1F2937",   // user bubble fill (dark slate, white text)
        border:    "#E7E2D6",   // soft beige border
        borderStrong: "#D6CFC0",
        fg:        "#1C1917",   // primary text (warm near-black)
        dim:       "#78716C",   // secondary text (warm gray)
        muted:     "#A8A29E",
        accent:    "#0F766E",   // teal — Approve / success
        accentSoft:"#CCFBF1",
        warn:      "#B45309",   // amber-700
        warnSoft:  "#FEF3C7",
        err:       "#B91C1C",
        errSoft:   "#FEE2E2",
        info:      "#1D4ED8",
        infoSoft:  "#DBEAFE",
        brand:     "#C2410C",   // burnt orange — header accent
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        soft: "0 1px 3px rgba(28, 25, 23, 0.06), 0 1px 2px rgba(28, 25, 23, 0.04)",
        card: "0 4px 12px rgba(28, 25, 23, 0.06)",
      },
      keyframes: {
        fadeUp: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "translateY(0)" } },
        blink:  { "0%,50%": { opacity: "1" }, "50.01%,100%": { opacity: "0" } },
      },
      animation: {
        fadeUp: "fadeUp 0.2s ease-out both",
        blink:  "blink 1.1s steps(1) infinite",
      },
    },
  },
  plugins: [],
};
