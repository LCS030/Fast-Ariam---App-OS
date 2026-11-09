// Normaliza parametros do expo-router (podem vir como string ou string[]).

export function paramStr(valor: string | string[] | undefined): string {
  if (Array.isArray(valor)) return valor[0] ?? "";
  return valor ?? "";
}

/** Numero finito ou null (nunca NaN). */
export function paramNum(valor: string | string[] | undefined): number | null {
  const s = paramStr(valor).trim();
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
