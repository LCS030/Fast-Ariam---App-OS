// Tipos da operacao offline-first (SDD 6.12, PRD 6.9).

/** Tipos de evento aceitos por POST /api/sync/eventos (SDD 6.12). */
export type TipoEvento =
  | "deslocamento_ida_iniciado"
  | "deslocamento_ida_finalizado"
  | "atendimento_iniciado"
  | "servico_salvo"
  | "conserto_salvo"
  | "foto_servico"
  | "comprovante_registrado"
  | "pausa_registrada"
  | "atendimento_finalizado"
  | "deslocamento_volta_iniciado"
  | "deslocamento_volta_finalizado";

/** Valores de tipo_arquivo de POST /api/sync/arquivos. */
export type TipoArquivo =
  | "foto_defeito"
  | "foto_conserto"
  | "foto_deslocamento"
  | "comprovante_pedagio"
  | "comprovante_frete"
  | "assinatura";

/**
 * pendente  = ainda nao confirmado pelo servidor (inclui ARQUIVO_AUSENTE, que e transitorio).
 * enviado   = servidor respondeu aplicado/duplicado.
 * rejeitado = servidor recusou (codigo/detalhe) ou o app nao conseguiu enviar de forma definitiva.
 */
export type StatusFila = "pendente" | "enviado" | "rejeitado";

export interface EventoOutbox {
  seq: number;
  client_event_id: string;
  id_tecnico: number;
  tipo: TipoEvento;
  id_os: number;
  id_visita: number;
  /** ISO-8601 com fuso, do relogio do aparelho no momento da acao (AR-05, RN-35). */
  ocorrido_em: string;
  ocorrido_ms: number;
  payload: Record<string, unknown>;
  status: StatusFila;
  codigo: string | null;
  detalhe: string | null;
  tentativas: number;
  /** Texto para identificar a OS na lista de pendencias mesmo depois que ela sair do cache. */
  rotulo_os: string | null;
  criado_ms: number;
  enviado_ms: number | null;
  /** O tecnico ja tratou a rejeicao (reenviou ou dispensou). A linha NUNCA e apagada. */
  tratado: boolean;
  /** client_event_id do evento rejeitado que este reenvia (SY-08). */
  reenvio_de: string | null;
}

export interface ArquivoOutbox {
  seq: number;
  client_file_id: string;
  id_tecnico: number;
  tipo_arquivo: TipoArquivo;
  /** null depois que o arquivo foi confirmado pelo servidor e liberado do aparelho. */
  caminho_local: string | null;
  mime: "image/jpeg" | "image/png";
  id_os: number;
  id_visita: number;
  status: StatusFila;
  codigo: string | null;
  detalhe: string | null;
  url: string | null;
  tentativas: number;
  criado_ms: number;
}

/** Erro de regra local (nao e erro de rede). A tela mostra a mensagem. */
export class ErroOffline extends Error {
  codigo: string;
  constructor(codigo: string, mensagem: string) {
    super(mensagem);
    this.name = "ErroOffline";
    this.codigo = codigo;
  }
}

/** Itens do payload que apontam para arquivos da fila. */
export function refsDoPayload(payload: Record<string, unknown>): string[] {
  const refs: string[] = [];
  for (const campo of ["foto_ref", "assinatura_ref"]) {
    const v = payload[campo];
    if (typeof v === "string" && v) refs.push(v);
  }
  return refs;
}

/** Rotulos legiveis dos tipos de evento (tela de pendencias e selos). */
export const ROTULO_EVENTO: Record<TipoEvento, string> = {
  deslocamento_ida_iniciado: "Início do deslocamento (ida)",
  deslocamento_ida_finalizado: "Fim do deslocamento (ida)",
  atendimento_iniciado: "Início do atendimento",
  servico_salvo: "Registro do atendimento",
  conserto_salvo: "Conserto salvo",
  foto_servico: "Foto do equipamento",
  comprovante_registrado: "Comprovante (pedágio/frete)",
  pausa_registrada: "Pausa da OS",
  atendimento_finalizado: "Fim do atendimento e assinatura",
  deslocamento_volta_iniciado: "Início do deslocamento (volta)",
  deslocamento_volta_finalizado: "Fim do deslocamento (volta)",
};

/** Explicacao curta por codigo de rejeicao (SDD 6.12); o detalhe do servidor e exibido junto. */
export const MOTIVO_CODIGO: Record<string, string> = {
  OS_CANCELADA: "A OS foi cancelada.",
  OS_PAUSADA: "A OS estava pausada e não aceitou esta ação.",
  OS_REATRIBUIDA: "A OS não é mais sua ou a visita não é mais a executável.",
  CONFLITO_ADMINISTRATIVO:
    "Conflito com uma alteração do administrador. A OS voltou para Pendente para nova atribuição.",
  TRANSICAO_INVALIDA: "A ação não era válida no estado em que a OS estava no servidor.",
  DEPENDENCIA_REJEITADA: "Uma ação anterior desta visita foi rejeitada.",
  FOTO_DEFEITO_AUSENTE: "Falta a foto do defeito de algum equipamento.",
  CONSERTO_INCOMPLETO: "Falta salvar o conserto ou a foto do conserto de algum equipamento.",
  ARQUIVO_AUSENTE: "Aguardando o envio da foto/assinatura.",
  ARQUIVO_REJEITADO: "A foto/assinatura desta ação foi recusada pelo servidor.",
  VALIDACAO: "O servidor recusou os dados desta ação.",
};
