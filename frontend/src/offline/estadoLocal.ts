// Estado LOCAL da visita (SDD 6.12 "Estado da visita offline").
//
// Modulo unico que calcula, a partir do ULTIMO estado devolvido pelo servidor
// (GET .../estado, via /sync/minhas-os) + os eventos ainda nao refletidos nele, os mesmos campos
// de EstadoVisita (6.6.3). Espelha `calcular_estado` e as travas TR-12/TR-13 do backend
// (visita_service.py / equipamento_service.py). E CONVENIENCIA DE TELA: o servidor continua
// sendo a autoridade e pode rejeitar o evento (SY-02, SY-08).
//
// Funcoes puras (sem I/O) para poderem ser verificadas isoladamente.
import type { ServicoEquipamento, Visita } from "@/api/chamado";
import type { EquipamentoEstado, EstadoVisita } from "@/api/visitas";
import type { EventoOutbox } from "./tipos";

export const MSG_OS_SEM_EQUIPAMENTO =
  "OS sem equipamento vinculado: o administrador precisa vincular ao menos um equipamento " +
  "(modelo + número de série) à OS.";

interface Fatos {
  status: string;
  idaIni: boolean;
  idaFim: boolean;
  atIni: boolean;
  atFim: boolean;
  voIni: boolean;
  voFim: boolean;
  pausada: boolean;
  motivoPausa: string | null;
  equipamentos: EquipamentoEstado[];
}

/** Deduz em que ponto da visita o servidor estava a partir dos flags de GET .../estado. */
function fatosDoServidor(status: string, e: EstadoVisita): Fatos {
  const pausada = !!e.is_os_pausada;
  const voFim = !!e.pode_concluir_chamado;
  const voEmAndamento = !!e.pode_finalizar_deslocamento_volta;
  const voPossivel = !!e.pode_iniciar_deslocamento_volta;

  // Sem o campo novo (servidor antigo): mesma heuristica que as telas usavam.
  const emAtendimento =
    e.atendimento_em_andamento ??
    (status === "Em Atendimento" && !voPossivel && !voEmAndamento && !voFim && !pausada);

  let atIni = false;
  let atFim = false;
  if (emAtendimento || pausada) {
    atIni = true; // pausa so existe com atendimento iniciado e nao finalizado
  } else if (voPossivel || voEmAndamento || voFim) {
    atIni = true;
    atFim = true;
  }

  const idaIni = !e.pode_iniciar_deslocamento_ida;
  const idaFim = idaIni && !e.pode_finalizar_deslocamento_ida;

  return {
    status,
    idaIni,
    idaFim,
    atIni,
    atFim,
    voIni: voFim || voEmAndamento,
    voFim,
    pausada,
    motivoPausa: e.motivo_pausa ?? null,
    equipamentos: e.equipamentos.map((q) => ({ ...q })),
  };
}

function acharEquip(f: Fatos, payload: Record<string, unknown>): EquipamentoEstado | undefined {
  const idServico = Number(payload.id_servico);
  if (Number.isFinite(idServico)) {
    const porServico = f.equipamentos.find((q) => q.id_servico === idServico);
    if (porServico) return porServico;
  }
  const idOsEquip = Number(payload.id_os_equipamento);
  if (Number.isFinite(idOsEquip)) {
    return f.equipamentos.find((q) => q.id_os_equipamento === idOsEquip);
  }
  return undefined;
}

function emAtendimentoDe(f: Fatos): boolean {
  return f.atIni && !f.atFim && !f.voFim;
}

function bloqueioIniciar(f: Fatos): string | null {
  if (f.equipamentos.length === 0) return MSG_OS_SEM_EQUIPAMENTO;
  const pend = f.equipamentos.filter((q) => !q.foto_defeito);
  if (pend.length === 0) return null;
  return (
    "Não é possível iniciar o atendimento sem foto do defeito de cada equipamento. " +
    `Pendentes: ${pend.map((q) => `${q.modelo} (série ${q.numero_serie})`).join("; ")}.`
  );
}

function bloqueioFinalizar(f: Fatos): string | null {
  if (f.equipamentos.length === 0) return MSG_OS_SEM_EQUIPAMENTO;
  const pend = f.equipamentos.filter((q) => !(q.conserto_salvo && q.foto_conserto));
  if (pend.length === 0) return null;
  const faltas = pend.map((q) => {
    const partes: string[] = [];
    if (!q.conserto_salvo) partes.push("conserto não salvo");
    if (!q.foto_conserto) partes.push("sem foto do conserto");
    return `${q.modelo} (série ${q.numero_serie}): ${partes.join(", ")}`;
  });
  return (
    "Não é possível finalizar o atendimento sem salvar o conserto e a foto do conserto de cada " +
    `equipamento. Pendentes: ${faltas.join("; ")}.`
  );
}

/** Aplica um evento aos fatos, SOMENTE se o servidor o aceitaria neste ponto (mesmas guardas). */
function aplicarEvento(f: Fatos, ev: EventoOutbox): void {
  const emAt = emAtendimentoDe(f);
  switch (ev.tipo) {
    case "deslocamento_ida_iniciado":
      if (!f.idaIni && !f.voFim && f.status === "Agendado") f.idaIni = true;
      break;
    case "deslocamento_ida_finalizado":
      if (f.idaIni && !f.idaFim) f.idaFim = true;
      break;
    case "atendimento_iniciado":
      if (f.idaFim && !f.atIni && !f.voFim && f.status === "Agendado" && bloqueioIniciar(f) === null) {
        f.atIni = true;
        f.status = "Em Atendimento";
      }
      break;
    case "foto_servico": {
      const q = acharEquip(f, ev.payload);
      if (!q) break;
      if (ev.payload.tipo === "defeito") {
        // v0.5: aceito com a visita aberta, atendimento nao finalizado e OS Agendado/Em Atendimento.
        if (!f.voFim && !f.atFim && (f.status === "Agendado" || f.status === "Em Atendimento")) {
          q.foto_defeito = true;
        }
      } else if (ev.payload.tipo === "conserto") {
        if (emAt && !f.pausada) q.foto_conserto = true; // so Em Atendimento (PR-42)
      }
      break;
    }
    case "conserto_salvo": {
      const q = acharEquip(f, ev.payload);
      if (q && emAt && !f.pausada) q.conserto_salvo = true;
      break;
    }
    case "pausa_registrada":
      if (emAt && !f.pausada) {
        f.pausada = true;
        f.motivoPausa = String(ev.payload.motivo ?? "") || null;
        f.status = "Pausado";
      }
      break;
    case "atendimento_finalizado":
      if (emAt && !f.pausada && bloqueioFinalizar(f) === null) f.atFim = true;
      break;
    case "deslocamento_volta_iniciado":
      if (!f.voIni && !f.voFim && (f.atFim || (f.pausada && f.atIni))) f.voIni = true;
      break;
    case "deslocamento_volta_finalizado":
      if (f.voIni && !f.voFim) {
        f.voFim = true;
        // RF-14: sem pausa ativa a OS finaliza; com pausa aguarda o reagendamento.
        f.status = f.pausada ? "Aguardando Reagendamento" : "Finalizado";
      }
      break;
    default:
      break; // servico_salvo e comprovante_registrado nao mudam o fluxo
  }
}

/** Monta EstadoVisita a partir dos fatos (espelho de calcular_estado, visita vigente). */
function estadoDeFatos(f: Fatos): EstadoVisita {
  const finalizada = f.voFim;
  const emAt = emAtendimentoDe(f);
  const bIni = bloqueioIniciar(f);
  const bFim = bloqueioFinalizar(f);
  const baseIniciar = f.idaFim && !f.atIni && !finalizada && f.status === "Agendado";
  const baseFinalizar = emAt && !f.pausada;
  return {
    visita_vigente: true,
    pode_iniciar_deslocamento_ida: !f.idaIni && !finalizada && f.status === "Agendado",
    pode_finalizar_deslocamento_ida: f.idaIni && !f.idaFim,
    pode_iniciar_atendimento: baseIniciar && bIni === null,
    pode_finalizar_atendimento: baseFinalizar && bFim === null,
    pode_registrar_foto_defeito:
      !finalizada && !f.atFim && (f.status === "Agendado" || f.status === "Em Atendimento"),
    atendimento_em_andamento: emAt,
    bloqueio_iniciar_atendimento: baseIniciar ? bIni : null,
    bloqueio_finalizar_atendimento: baseFinalizar ? bFim : null,
    equipamentos: f.equipamentos,
    pode_iniciar_deslocamento_volta:
      !f.voIni && !finalizada && (f.atFim || (f.pausada && f.atIni)),
    pode_finalizar_deslocamento_volta: f.voIni && !f.voFim,
    pode_concluir_chamado: f.voFim,
    pode_pausar_os: emAt && !f.pausada,
    is_os_pausada: f.pausada,
    motivo_pausa: f.motivoPausa,
  };
}

export interface ResultadoEstadoLocal {
  status: string;
  estado: EstadoVisita | null;
}

/**
 * Estado da visita vigente = ultimo estado do servidor + eventos locais ainda nao refletidos.
 * `eventos` deve estar em ordem de envio (ocorrido_em, depois ordem de gravacao).
 */
export function calcularEstadoLocal(
  status: string,
  base: EstadoVisita | null,
  idVisita: number | undefined,
  eventos: EventoOutbox[]
): ResultadoEstadoLocal {
  if (!base || idVisita === undefined) return { status, estado: base };
  // Visita de historico / OS sem tecnico: nada a sobrepor.
  if (base.visita_vigente === false) return { status, estado: base };

  const fatos = fatosDoServidor(status, base);
  for (const ev of eventos) {
    if (ev.id_visita !== idVisita) continue;
    aplicarEvento(fatos, ev);
  }
  return { status: fatos.status, estado: estadoDeFatos(fatos) };
}

// ---------------------------------------------------------------------------------------------
// Servicos e valores da visita (para as telas de registro e de pedagio/frete)
// ---------------------------------------------------------------------------------------------

/** Servicos da visita com os registros ainda nao enviados sobrepostos (ultimo salvo vence). */
export function servicosLocais(
  visita: Visita | undefined,
  estado: EstadoVisita | null,
  eventos: EventoOutbox[]
): ServicoEquipamento[] {
  if (!visita) return [];
  let servicos: ServicoEquipamento[] = (visita.servicos_realizados ?? []).map((s) => ({ ...s }));

  // Cache sem servicos detalhados: usa a lista do estado para a tela abrir mesmo assim.
  if (servicos.length === 0 && estado) {
    servicos = estado.equipamentos.map((q) => ({
      id_servico: q.id_servico,
      id_os_equipamento: q.id_os_equipamento,
      modelo: q.modelo,
      numero_serie: q.numero_serie,
      conserto_salvo_em: null,
    }));
  }

  for (const ev of eventos) {
    if (ev.id_visita !== visita.id_visita) continue;
    if (ev.tipo !== "servico_salvo" && ev.tipo !== "conserto_salvo") continue;
    const alvo = servicos.find(
      (s) =>
        (ev.payload.id_servico !== undefined && s.id_servico === Number(ev.payload.id_servico)) ||
        (ev.payload.id_os_equipamento !== undefined &&
          s.id_os_equipamento === Number(ev.payload.id_os_equipamento))
    );
    if (!alvo) continue;
    if (ev.tipo === "servico_salvo") {
      const { id_servico: _a, id_os_equipamento: _b, ...campos } = ev.payload;
      Object.assign(alvo, campos);
    } else if (!alvo.conserto_salvo_em) {
      alvo.conserto_salvo_em = ev.ocorrido_em;
    }
  }
  return servicos;
}

export interface DespesasLocais {
  valor_pedagio: number;
  valor_frete: number;
  /** Comprovantes (fotos) registrados no servidor + na fila. */
  comprovantes_pedagio: number;
  comprovantes_frete: number;
  /** Quantos desses ainda aguardam envio. */
  comprovantes_pendentes: number;
}

export function despesasLocais(visita: Visita | undefined, eventos: EventoOutbox[]): DespesasLocais {
  const d: DespesasLocais = {
    valor_pedagio: Number(visita?.valor_pedagio ?? 0),
    valor_frete: Number(visita?.valor_frete_devolucao ?? 0),
    comprovantes_pedagio: visita?.comprovante_pedagio_urls?.length ?? 0,
    comprovantes_frete: visita?.comprovante_frete_urls?.length ?? 0,
    comprovantes_pendentes: 0,
  };
  if (!visita) return d;
  for (const ev of eventos) {
    if (ev.tipo !== "comprovante_registrado" || ev.id_visita !== visita.id_visita) continue;
    const valor = ev.payload.valor === undefined ? null : Number(ev.payload.valor);
    if (ev.payload.tipo === "pedagio") {
      if (valor !== null) d.valor_pedagio = valor;
      d.comprovantes_pedagio += 1;
    } else if (ev.payload.tipo === "frete") {
      if (valor !== null) d.valor_frete = valor;
      d.comprovantes_frete += 1;
    }
    if (ev.status === "pendente") d.comprovantes_pendentes += 1;
  }
  return d;
}

/** KM inicial de cada perna (servidor + eventos locais), para validar o KM final no aparelho. */
export function kmIniciaisLocais(
  visita: Visita | undefined,
  eventos: EventoOutbox[]
): { ida: number | null; volta: number | null } {
  const km = { ida: visita?.km_inicio_ida ?? null, volta: visita?.km_inicio_volta ?? null };
  if (!visita) return km;
  for (const ev of eventos) {
    if (ev.id_visita !== visita.id_visita) continue;
    const valor = Number(ev.payload.km_inicio);
    if (!Number.isFinite(valor)) continue;
    if (ev.tipo === "deslocamento_ida_iniciado") km.ida = valor;
    if (ev.tipo === "deslocamento_volta_iniciado") km.volta = valor;
  }
  return km;
}
