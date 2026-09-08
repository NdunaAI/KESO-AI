import type { Config } from "tailwindcss";

// Brand palette lifted from https://www.kuhlesolutions.net/ (see the
// KESO Assistant Chat UI design canvas) -- keep these in sync with any
// future brand refresh rather than inventing new hex values ad hoc.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        keso: {
          orange: "#F26E24",
          "orange-dark": "#D85E1A",
          "orange-tint": "#FDEEE4",
          indigo: "#494395",
          "indigo-dark": "#3A3578",
          "indigo-tint": "#ECEBF6",
          green: "#8DC440",
          "green-dark": "#74A430",
          "green-tint": "#EFF7E4",
          teal: "#73A5AD",
          ink: "#2A2A38",
          "ink-muted": "#6B6B7B",
          "ink-faint": "#9C9CAC",
          border: "#E4E4EC",
          "border-soft": "#EFEFF4",
          surface: "#FAFAFC",
          page: "#F7F7FA",
        },
      },
      fontFamily: {
        sans: ["var(--font-noto-sans)", "system-ui", "-apple-system", "sans-serif"],
      },
      borderRadius: {
        chip: "999px",
      },
    },
  },
  plugins: [],
};

export default config;
