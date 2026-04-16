export const color = {
  surface: { 0: "#ffffff", 1: "#fafafa", 2: "#f5f5f5", 3: "#ebebeb", 4: "#d5d5d5" },
  txt: { primary: "#010101", secondary: "#333333", muted: "#777777", inverse: "#ffffff" },
  signal: {
    malaria:      "#ED7238",
    arbovirus:    "#FF8951",
    conflict:     "#dc2626",
    funding:      "#1d499e",
    climate:      "#5B8FF4",
    surveillance: "#19bdc3",
  },
  uncertainty: {
    low:       "#1d499e",
    moderate:  "#ED7238",
    high:      "#ef6801",
    very_high: "#dc2626",
  },
  accent: {
    orange: "#ED7238",
    navy:   "#1d499e",
    teal:   "#19bdc3",
    blue:   "#5B8FF4",
    yellow: "#f5ec51",
    dark:   "#2c3277",
  },
} as const;

export const ALERT_LEVELS = {
  extreme:  { label: "Extreme",  color: "#7c3aed" },
  critical: { label: "Critical", color: "#dc2626" },
  high:     { label: "High",     color: "#ef6801" },
  moderate: { label: "Moderate", color: "#ED7238" },
  low:      { label: "Low",      color: "#1d499e" },
} as const;

export const EVENT_COLORS: Record<string, string> = {
  arbovirus:   "#FF8951",
  hemorrhagic: "#dc2626",
  bacterial:   "#7c3aed",
  conflict:    "#dc2626",
  respiratory: "#4f46e5",
} as const;

export const font = {
  display: "'ff-tisa-web-pro', Georgia, serif",
  gothic:  "'League Gothic', 'LeagueGothic', 'Arial Narrow', sans-serif",
  mono:    "'IBM Plex Mono', 'SFMono-Regular', monospace",
} as const;

export const motion = {
  fast:     "120ms",
  enter:    "180ms",
  standard: "240ms",
  slow:     "360ms",
} as const;

/** Chapter metadata — single source of truth for nav + pages */
export const CHAPTERS = [
  {
    id:    "command",
    href:  "/command",
    label: "Command",
    desc:  "The global malaria threat landscape",
    color: color.signal.conflict,
  },
  {
    id:    "investment",
    href:  "/investment",
    label: "Investment",
    desc:  "How much America commits",
    color: color.accent.orange,
  },
  {
    id:    "flows",
    href:  "/flows",
    label: "Flows",
    desc:  "Where every dollar goes",
    color: color.accent.navy,
  },
  {
    id:    "impact",
    href:  "/impact",
    label: "Impact",
    desc:  "What the investment achieved",
    color: color.accent.blue,
  },
  {
    id:    "us-ecosystem",
    href:  "/us-ecosystem",
    label: "US Ecosystem",
    desc:  "Who in America does this work",
    color: color.accent.teal,
  },
  {
    id:    "outlook",
    href:  "/outlook",
    label: "Outlook",
    desc:  "Gaps, risks, and what's at stake",
    color: color.signal.conflict,
  },
] as const;
