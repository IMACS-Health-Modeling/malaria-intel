import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          0: "#ffffff",
          1: "#fafafa",
          2: "#f5f5f5",
          3: "#ebebeb",
          4: "#d5d5d5",
        },
        txt: {
          primary: "#010101",
          secondary: "#333333",
          muted: "#777777",
          inverse: "#ffffff",
        },
        signal: {
          malaria: "#ED7238",
          arbovirus: "#FF8951",
          conflict: "#dc2626",
          funding: "#1d499e",
          climate: "#5B8FF4",
          surveillance: "#19bdc3",
        },
        uncertainty: {
          low: "#1d499e",
          moderate: "#ED7238",
          high: "#ef6801",
          "very-high": "#dc2626",
        },
        accent: {
          DEFAULT: "#5B8FF4",
          hover: "#2b6ef1",
          orange: "#ED7238",
          navy: "#1d499e",
          teal: "#19bdc3",
          yellow: "#f5ec51",
          dark: "#2c3277",
        },
      },
      fontFamily: {
        sans:    ["'ff-tisa-web-pro'", "Georgia", "'Times New Roman'", "serif"],
        display: ["'ff-tisa-web-pro'", "Georgia", "'Times New Roman'", "serif"],
        gothic:  ["'League Gothic'", "'LeagueGothic'", "'Arial Narrow'", "sans-serif"],
        mono:    ["'IBM Plex Mono'", "'SFMono-Regular'", "Consolas", "monospace"],
      },
      fontSize: {
        "2xs": ["11px", { lineHeight: "1.3" }],
        xs:    ["13px", { lineHeight: "1.5" }],
        sm:    ["15px", { lineHeight: "1.6" }],
        base:  ["17px", { lineHeight: "1.8" }],
        lg:    ["20px", { lineHeight: "1.5" }],
        xl:    ["24px", { lineHeight: "1.3" }],
        "2xl": ["30px", { lineHeight: "1.2" }],
        "3xl": ["40px", { lineHeight: "1.1" }],
        "4xl": ["52px", { lineHeight: "1.0" }],
      },
      borderRadius: {
        micro: "2px",
        badge: "4px",
        panel: "8px",
        modal: "12px",
        pill:  "999px",
      },
      boxShadow: {
        card:        "0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)",
        "card-hover":"0 4px 12px rgba(0,0,0,0.10), 0 2px 4px rgba(0,0,0,0.06)",
        map:         "0 4px 24px rgba(0,0,0,0.08)",
        overlay:     "0 10px 40px rgba(0,0,0,0.12)",
        modal:       "0 18px 70px rgba(0,0,0,0.16)",
        glow:        "0 0 20px rgba(237,114,56,0.15)",
        "glow-blue": "0 0 20px rgba(91,143,244,0.15)",
      },
      animation: {
        "pulse-slow":     "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "pulse-ring":     "pulse-ring 2s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":        "fade-in 0.5s ease-out",
        "slide-up":       "slide-up 0.4s cubic-bezier(0.2,0,0,1)",
        "count-up":       "fade-in 0.8s ease-out",
        "ticker-scroll":  "ticker-scroll 60s linear infinite",
      },
      keyframes: {
        "pulse-ring": {
          "0%":   { transform: "scale(1)", opacity: "0.6" },
          "100%": { transform: "scale(2.5)", opacity: "0" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to:   { opacity: "1" },
        },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(12px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        "ticker-scroll": {
          from: { transform: "translateX(0)" },
          to:   { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
