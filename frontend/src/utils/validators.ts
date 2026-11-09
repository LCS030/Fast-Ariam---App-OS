// Validacoes locais de formulario. O servidor sempre revalida (nunca e a autoridade).

export function soDigitos(valor: string): string {
  return valor.replace(/\D/g, "");
}

/** Mascara progressiva 000.000.000-00 (aceita colagem com ou sem pontuacao). */
export function mascararCpf(valor: string): string {
  const d = soDigitos(valor).slice(0, 11);
  if (d.length <= 3) return d;
  if (d.length <= 6) return `${d.slice(0, 3)}.${d.slice(3)}`;
  if (d.length <= 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
  return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
}

/** CPF valido: 11 digitos, nao repetidos, digitos verificadores corretos (RN-23). */
export function cpfValido(valor: string): boolean {
  const d = soDigitos(valor);
  if (d.length !== 11) return false;
  if (/^(\d)\1{10}$/.test(d)) return false;

  const digito = (base: string, pesoInicial: number): number => {
    let soma = 0;
    for (let i = 0; i < base.length; i++) {
      soma += Number(base[i]) * (pesoInicial - i);
    }
    const resto = (soma * 10) % 11;
    return resto === 10 ? 0 : resto;
  };

  return digito(d.slice(0, 9), 10) === Number(d[9]) && digito(d.slice(0, 10), 11) === Number(d[10]);
}

/** KM: inteiro nao negativo (o contrato usa inteiro). Retorna null se invalido. */
export function parseKm(texto: string): number | null {
  const t = texto.trim();
  if (!/^\d{1,9}$/.test(t)) return null;
  return Number(t);
}

/** Valor monetario >= 0 aceitando virgula ou ponto. Vazio conta como 0. Null se invalido. */
export function parseValor(texto: string): number | null {
  const t = texto.trim().replace(",", ".");
  if (t === "") return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Number(t);
}
