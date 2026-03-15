// File: src/styles/Colors.ts
// Path: src/styles/Colors.ts

export const colors = {
  gray: {
    100: "#F4F4F5",
    200: "#E9ECEF",
    400: "#A1A1AA",
    500: "#71717A",
    800: "#27272A",
    950: "#09090B",
  },

  blue: {
    900: "#194869",
    500: "#1E90FF",
  },

  red: {
    500: "#FF0000",
    900: "#CC0000",
  },

  green: {
    500: "#4CAF50",
  },

  action: {
    primary: "#007BFF",
    text: "#FFFFFF",
  },
} as const;

export type Colors = typeof colors;
