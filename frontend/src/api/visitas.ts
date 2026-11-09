// ATENCAO (offline-first, AR-04): as telas NAO chamam mais as funcoes de acao deste arquivo
// diretamente. Toda acao passa por src/offline/acoes.ts (grava na fila e sincroniza via
// /api/sync). Aqui permanecem os tipos do estado e o helper agoraIso(); as chamadas diretas
// abaixo sao mantidas apenas como referencia dos endpoints online equivalentes.
import api from "./api";
import { anexarImagem, ArquivoImagem, UPLOAD_TIMEOUT_MS } from "./arquivo";

/** Situacao de um equipamento da OS na visita vigente (SDD 6.6.3, v0.5). */
export interface EquipamentoEstado {
  id_os_equipamento: number;
  /** Ancora para upload-foto, PATCH e salvar-conserto. */
  id_servico: number;
  modelo: string;
  numero_serie: string;
  foto_defeito: boolean;
  conserto_salvo: boolean;
  foto_conserto: boolean;
}

/** Resposta de GET .../estado (SDD 6.6.3): fonte de verdade para os botoes do app. */
export interface EstadoVisita {
  pode_iniciar_deslocamento_ida: boolean;
  pode_finalizar_deslocamento_ida: boolean;
  pode_iniciar_atendimento: boolean;
  pode_finalizar_atendimento: boolean;
  pode_iniciar_deslocamento_volta: boolean;
  pode_finalizar_deslocamento_volta: boolean;
  /** Mantido no contrato apenas como indicador "volta concluida"; NAO existe conclusao manual. */
  pode_concluir_chamado: boolean;
  pode_pausar_os: boolean;
  is_os_pausada: boolean;
  motivo_pausa: string | null;
  /** v0.5: botao de foto do defeito liberado ANTES de iniciar o atendimento. */
  pode_registrar_foto_defeito: boolean;
  /** v0.5: texto do servidor com a pendencia que impede iniciar/finalizar; null = sem bloqueio. */
  bloqueio_iniciar_atendimento: string | null;
  bloqueio_finalizar_atendimento: string | null;
  /** v0.5: um item por equipamento da OS; [] em visita nao vigente. */
  equipamentos: EquipamentoEstado[];
  /** v0.5: atendimento iniciado e nao finalizado (inclusive pausado). Libera "Salvar conserto" e foto de conserto. */
  atendimento_em_andamento?: boolean;
  /** false = visita de historico ou OS sem tecnico: nenhuma acao. Ausente = tratar como true. */
  visita_vigente?: boolean;
}

/**
 * ISO-8601 com o offset local do aparelho, ex.: 2026-11-04T21:15:04-03:00 (RN-24).
 * Aceita uma data para facilitar teste; por padrao usa o instante atual.
 */
export function agoraIso(data: Date = new Date()): string {
  const p2 = (n: number) => String(n).padStart(2, "0");
  const off = -data.getTimezoneOffset(); // minutos a leste de UTC
  const sinal = off >= 0 ? "+" : "-";
  const abs = Math.abs(off);
  return (
    `${data.getFullYear()}-${p2(data.getMonth() + 1)}-${p2(data.getDate())}` +
    `T${p2(data.getHours())}:${p2(data.getMinutes())}:${p2(data.getSeconds())}` +
    `${sinal}${p2(Math.floor(abs / 60))}:${p2(abs % 60)}`
  );
}

const base = (chamadoId: number, visitaId: number) =>
  `/chamados/${chamadoId}/visitas/${visitaId}`;

export async function getEstadoVisita(chamadoId: number, visitaId: number) {
  const res = await api.get<EstadoVisita>(`${base(chamadoId, visitaId)}/estado`);
  const e = res.data;
  // Campos v0.5 ausentes (servidor antigo) viram "sem permissao/sem equipamento": nunca liberam acao.
  return {
    ...e,
    pode_registrar_foto_defeito: !!e.pode_registrar_foto_defeito,
    bloqueio_iniciar_atendimento: e.bloqueio_iniciar_atendimento ?? null,
    bloqueio_finalizar_atendimento: e.bloqueio_finalizar_atendimento ?? null,
    equipamentos: Array.isArray(e.equipamentos) ? e.equipamentos : [],
    atendimento_em_andamento: e.atendimento_em_andamento,
  };
}

// ===============================
// DESLOCAMENTO (IDA / VOLTA)
// ===============================
export async function iniciarDeslocamento(
  chamadoId: number,
  visitaId: number,
  data: { tipo: "ida" | "volta"; km_inicio: number },
  ocorridoEm: string = agoraIso()
) {
  const res = await api.post(`${base(chamadoId, visitaId)}/iniciar-deslocamento`, {
    ...data,
    ocorrido_em: ocorridoEm,
  });
  return res.data;
}

export async function finalizarDeslocamento(
  chamadoId: number,
  visitaId: number,
  tipo: "ida" | "volta",
  kmFim: number,
  ocorridoEm: string = agoraIso()
) {
  const res = await api.post(`${base(chamadoId, visitaId)}/finalizar-deslocamento`, {
    tipo,
    km_fim: kmFim,
    ocorrido_em: ocorridoEm,
  });
  return res.data;
}

/** Foto do odometro/deslocamento (sem resolucao minima; JPEG/PNG ate 15 MB). */
export async function uploadDeslocamento(
  chamadoId: number,
  visitaId: number,
  arquivo: ArquivoImagem,
  tipo: "ida" | "volta",
  momento: "inicio" | "fim"
) {
  const formData = new FormData();
  anexarImagem(formData, "file", arquivo, `odometro_${tipo}_${momento}`);
  formData.append("tipo", tipo);
  formData.append("momento", momento);

  const res = await api.post(`${base(chamadoId, visitaId)}/upload-deslocamento`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: UPLOAD_TIMEOUT_MS,
  });
  return res.data;
}

// ===============================
// ATENDIMENTO
// ===============================
export async function iniciarAtendimentoVisita(
  chamadoId: number,
  visitaId: number,
  ocorridoEm: string = agoraIso()
) {
  const res = await api.post(`${base(chamadoId, visitaId)}/iniciar-atendimento`, {
    ocorrido_em: ocorridoEm,
  });
  return res.data;
}

/** Finaliza o atendimento com nome, CPF (somente digitos) e assinatura (RN-22/RN-23). */
export async function finalizarAtendimento(
  chamadoId: number,
  visitaId: number,
  dados: { assinaturaBase64: string; nomeCliente: string; cpf: string },
  ocorridoEm: string = agoraIso()
) {
  const res = await api.post(`${base(chamadoId, visitaId)}/finalizar-atendimento`, {
    assinatura_base64: dados.assinaturaBase64,
    nome_cliente: dados.nomeCliente,
    documento_cliente: dados.cpf,
    ocorrido_em: ocorridoEm,
  });
  return res.data;
}

/** Pausa a visita. Motivo da lista oficial (RN-29); "Outro" exige descricao. */
export async function pausarVisita(
  chamadoId: number,
  visitaId: number,
  motivo: string,
  descricao?: string,
  ocorridoEm: string = agoraIso()
) {
  const payload: Record<string, string> = { motivo, ocorrido_em: ocorridoEm };
  if (descricao) payload.descricao = descricao;
  const res = await api.post(`${base(chamadoId, visitaId)}/pausar`, payload);
  return res.data;
}

// ===============================
// PEDAGIO / FRETE (RN-20)
// ===============================
export async function atualizarValoresVisita(
  chamadoId: number,
  visitaId: number,
  body: { valor_pedagio?: number; valor_frete_devolucao?: number }
) {
  const res = await api.patch(base(chamadoId, visitaId), body);
  return res.data;
}

export async function enviarComprovante(
  chamadoId: number,
  visitaId: number,
  tipo: "pedagio" | "frete",
  arquivo: ArquivoImagem
) {
  const formData = new FormData();
  anexarImagem(formData, "file", arquivo, `comprovante_${tipo}`);
  formData.append(
    "file_type",
    tipo === "pedagio" ? "comprovante_pedagio_urls" : "comprovante_frete_urls"
  );

  const res = await api.post(`${base(chamadoId, visitaId)}/upload_file`, formData, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: UPLOAD_TIMEOUT_MS,
  });
  return res.data;
}
