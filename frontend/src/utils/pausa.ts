// Lista oficial de motivos de pausa (PRD RN-29 / SDD secao 7). Mesma lista do painel e do backend.
export const MOTIVOS_PAUSA = [
  "Peça pendente",
  "Cliente ausente",
  "Condições inseguras",
  "Aguardando aprovação",
  "Outro",
] as const;

export type MotivoPausa = (typeof MOTIVOS_PAUSA)[number];

export const MOTIVO_OUTRO: MotivoPausa = "Outro";

/** Retorna a mensagem de erro de validacao local, ou null se o formulario e valido. */
export function validarPausa(motivo: string | null, descricao: string): string | null {
  if (!motivo) return "Selecione o motivo da pausa.";
  if (!(MOTIVOS_PAUSA as readonly string[]).includes(motivo)) return "Motivo de pausa inválido.";
  if (motivo === MOTIVO_OUTRO && descricao.trim().length === 0) {
    return 'Informe a descrição quando o motivo for "Outro".';
  }
  return null;
}
