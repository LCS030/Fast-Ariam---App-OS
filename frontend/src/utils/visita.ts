// Regras de apresentacao derivadas do estado devolvido pelo servidor.
// Nada aqui e regra de negocio autoritativa: o servidor valida cada acao (RN-16).
import type { Chamado, Visita } from "@/api/chamado";
import type { EstadoVisita } from "@/api/visitas";

/**
 * Uma OS pode ter varias visitas (reagendamento cria uma nova). A visita "atual" e a
 * ultima ainda nao finalizada; se todas estiverem finalizadas, a mais recente.
 */
export function escolherVisitaAtual(visitas?: Visita[] | null): Visita | undefined {
  if (!visitas || visitas.length === 0) return undefined;
  const porId = [...visitas].sort((a, b) => a.id_visita - b.id_visita);
  const aberta = [...porId].reverse().find((v) => !v.servico_finalizado);
  return aberta ?? porId[porId.length - 1];
}

/**
 * Botao principal: apenas deslocamentos. "Iniciar" e "Finalizar atendimento" tem botoes
 * proprios, sempre visiveis e desabilitados enquanto o servidor nao liberar (v0.5).
 */
export type AcaoPrincipal =
  | "iniciar_ida"
  | "finalizar_ida"
  | "iniciar_volta"
  | "finalizar_volta";

export interface UiVisita {
  /** Botao principal. null = nenhuma acao do tecnico no momento. */
  acao: AcaoPrincipal | null;
  textoAcao: string;
  /** Volta concluida apos pausa: tecnico aguarda o reagendamento pelo administrador. */
  aguardandoReagendamento: boolean;
  /** OS finalizada automaticamente ao fim da volta (RF-14). Nao existe conclusao manual. */
  finalizada: boolean;
  pausada: boolean;
  podePausar: boolean;
  /** pode_registrar_foto_defeito do servidor: vale ANTES de iniciar o atendimento. */
  podeFotoDefeito: boolean;
  /** Foto de conserto e "Registro do atendimento": somente com o atendimento em andamento. */
  podeRegistrarConserto: boolean;
  /** Registro de pedagio permitido enquanto a visita esta aberta e nao pausada. */
  visitaAberta: boolean;
  /** Botoes Iniciar/Finalizar atendimento: sempre visiveis na visita aberta e nao pausada. */
  mostrarBotoesAtendimento: boolean;
  podeIniciarAtendimento: boolean;
  podeFinalizarAtendimento: boolean;
  bloqueioIniciar: string | null;
  bloqueioFinalizar: string | null;
}

const TEXTOS: Record<AcaoPrincipal, string> = {
  iniciar_ida: "Iniciar deslocamento (ida)",
  finalizar_ida: "Finalizar deslocamento (ida)",
  iniciar_volta: "Iniciar deslocamento (volta)",
  finalizar_volta: "Finalizar deslocamento (volta)",
};

export function derivarUi(chamado: Chamado, estado: EstadoVisita | null): UiVisita {
  const vazio: UiVisita = {
    acao: null,
    textoAcao: "",
    aguardandoReagendamento: false,
    finalizada: false,
    pausada: false,
    podePausar: false,
    podeFotoDefeito: false,
    podeRegistrarConserto: false,
    visitaAberta: false,
    mostrarBotoesAtendimento: false,
    podeIniciarAtendimento: false,
    podeFinalizarAtendimento: false,
    bloqueioIniciar: null,
    bloqueioFinalizar: null,
  };
  if (!estado) return vazio;

  const pausada = !!estado.is_os_pausada;
  const voltaConcluida = !!estado.pode_concluir_chamado; // so indica "volta concluida"

  const aguardandoReagendamento =
    chamado.status === "Aguardando Reagendamento" || (pausada && voltaConcluida);
  const finalizada = chamado.status === "Finalizado" || (!pausada && voltaConcluida);

  if (aguardandoReagendamento || finalizada || chamado.is_cancelled) {
    return { ...vazio, aguardandoReagendamento, finalizada, pausada };
  }

  let acao: AcaoPrincipal | null = null;
  if (pausada) {
    // RN-27: pausada nao finaliza atendimento. RN-18: volta pode iniciar mesmo sem fim de atendimento.
    if (estado.pode_iniciar_deslocamento_volta) acao = "iniciar_volta";
    else if (estado.pode_finalizar_deslocamento_volta) acao = "finalizar_volta";
  } else if (estado.pode_iniciar_deslocamento_ida) acao = "iniciar_ida";
  else if (estado.pode_finalizar_deslocamento_ida) acao = "finalizar_ida";
  else if (estado.pode_iniciar_deslocamento_volta) acao = "iniciar_volta";
  else if (estado.pode_finalizar_deslocamento_volta) acao = "finalizar_volta";

  // Atendimento em andamento: indicador explicito do estado (v0.5, calculado no aparelho a partir
  // do servidor + acoes pendentes). Servidor antigo sem o campo: heuristica pelo status da OS.
  const emAtendimento =
    estado.atendimento_em_andamento ??
    (chamado.status === "Em Atendimento" &&
      !estado.pode_iniciar_deslocamento_volta &&
      !estado.pode_finalizar_deslocamento_volta);

  return {
    acao,
    textoAcao: acao ? TEXTOS[acao] : "",
    aguardandoReagendamento: false,
    finalizada: false,
    pausada,
    podePausar: !pausada && !!estado.pode_pausar_os,
    podeFotoDefeito: !pausada && !!estado.pode_registrar_foto_defeito,
    podeRegistrarConserto: !pausada && emAtendimento,
    visitaAberta: true,
    mostrarBotoesAtendimento: !pausada,
    podeIniciarAtendimento: !pausada && !!estado.pode_iniciar_atendimento,
    podeFinalizarAtendimento: !pausada && !!estado.pode_finalizar_atendimento,
    bloqueioIniciar: estado.bloqueio_iniciar_atendimento ?? null,
    bloqueioFinalizar: estado.bloqueio_finalizar_atendimento ?? null,
  };
}
