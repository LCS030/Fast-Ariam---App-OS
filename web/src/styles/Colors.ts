// File: src/styles/Colors.ts
// Path: src/styles/Colors.ts
//
// MESMA paleta do app mobile (frontend/src/styles/Colors.ts). Os valores de `gray`, `blue`, `red`, `green` e `action`
// são IDÊNTICOS aos do app. O index.css define os mesmos hex como variáveis CSS (tokens do Tailwind): ao mudar a
// identidade visual, altere os dois lugares.

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
    900: "#194869", // azul-marinho da marca (cabeçalho, títulos, botão secundário)
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

  // Extras do painel web (não existem no app): variantes de texto derivadas, só para contraste. O painel não usa degradês.
  web: {
    primaryText: "#0065CF", // #007BFF um tom mais escuro: texto pequeno sobre fundo claro (>= 4,5:1)
    successText: "#2E7D32", // #4CAF50 um tom mais escuro: texto pequeno sobre fundo claro (>= 4,5:1)
    successOnNavy: "#7FC784", // verde legível sobre o marinho
  },
} as const;

export type Colors = typeof colors;
