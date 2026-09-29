/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#080b13",
          900: "#0d1320",
          800: "#141c2e",
          700: "#1d2840",
          600: "#2a3858",
        },
        walnut: {
          950: "#140e0a",
          900: "#1c140e",
          800: "#271b13",
          700: "#35251a",
          600: "#4a3424",
        },
        brass: {
          200: "#f7e4b0",
          300: "#f0d27f",
          400: "#e3b957",
          500: "#c89b3c",
          600: "#9c772b",
          700: "#6e531e",
          800: "#473612",
        },
        parchment: {
          50: "#fbf7ee",
          100: "#f3ead6",
          200: "#e3d5b6",
          300: "#cbbb97",
          400: "#a8997a",
          500: "#857a62",
          600: "#62594a",
        },
        verdict: {
          green: "#6cc792",
          amber: "#e6a93f",
          red: "#e8705f",
          gray: "#8e94a0",
        },
      },
      fontFamily: {
        display: ['"Cormorant Garamond"', "Georgia", "serif"],
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "Menlo", "monospace"],
      },
      boxShadow: {
        brass: "0 0 0 1px rgba(200,155,60,0.35), 0 10px 30px -12px rgba(0,0,0,0.7)",
        glow: "0 0 24px -4px rgba(240,210,127,0.55)",
      },
      keyframes: {
        caret: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0" } },
        rise: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        caret: "caret 1s steps(1) infinite",
        rise: "rise 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};
