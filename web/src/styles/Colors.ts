// File: src/styles/Colors.ts
// Path: src/styles/Colors.ts

export const colors = {
  brand: {
    navyDeep: "oklch(0.21 0.035 252)",
    navy: "oklch(0.29 0.06 248)",
    navyMedium: "oklch(0.38 0.075 246)",
    redFast: "oklch(0.56 0.205 27)",
    redFastBright: "oklch(0.62 0.19 27)",
    white: "oklch(1 0 0)",
  },
  gray: {
    100: "oklch(0.98 0.004 250)",
    200: "oklch(0.945 0.012 248)",
    400: "oklch(0.72 0.02 250)",
    500: "oklch(0.52 0.025 250)",
    800: "oklch(0.3 0.04 252)",
    950: "oklch(0.18 0.03 252)",
  },
  blue: {
    900: "oklch(0.29 0.06 248)",
    500: "oklch(0.38 0.075 246)",
  },
  red: {
    500: "oklch(0.56 0.205 27)",
    900: "oklch(0.45 0.22 27)",
  },
  green: {
    500: "oklch(0.62 0.13 155)",
  },
  action: {
    primary: "oklch(0.56 0.205 27)",
    text: "#FFFFFF",
  },
} as const;

export type Colors = typeof colors;

