// Estado global leve da operacao offline: conexao, contagens da fila e sessao.
// Sem biblioteca extra: useSyncExternalStore sobre um objeto imutavel.
import { useSyncExternalStore } from "react";
import type { SituacaoSessao } from "./sessao";

export interface StatusOffline {
  /** Conexao com a internet (NetInfo). */
  online: boolean;
  sincronizando: boolean;
  /** Acoes (eventos) ainda nao confirmadas pelo servidor. */
  pendentes: number;
  /** Fotos/assinaturas ainda nao enviadas. */
  arquivosPendentes: number;
  /** Acoes rejeitadas que o tecnico ainda nao tratou. */
  rejeitadas: number;
  situacaoSessao: SituacaoSessao;
  /** Ultima sincronizacao completa (ms) ou null. */
  ultimoSync: number | null;
  /** Mensagem da ultima falha de envio (rede/servidor), ou null. */
  erroSync: string | null;
}

let status: StatusOffline = {
  online: true,
  sincronizando: false,
  pendentes: 0,
  arquivosPendentes: 0,
  rejeitadas: 0,
  situacaoSessao: "sem_sessao",
  ultimoSync: null,
  erroSync: null,
};

let versao = 0;
const ouvintesStatus = new Set<() => void>();
const ouvintesVersao = new Set<() => void>();

export function getStatus(): StatusOffline {
  return status;
}

export function atualizarStatus(parcial: Partial<StatusOffline>): void {
  const mudou = (Object.keys(parcial) as (keyof StatusOffline)[]).some(
    (k) => status[k] !== parcial[k]
  );
  if (!mudou) return;
  status = { ...status, ...parcial };
  ouvintesStatus.forEach((l) => l());
}

/** Avisa as telas que os dados locais (cache/filas) mudaram e devem ser relidos. */
export function notificarMudancaLocal(): void {
  versao += 1;
  ouvintesVersao.forEach((l) => l());
}

function assinarStatus(l: () => void) {
  ouvintesStatus.add(l);
  return () => {
    ouvintesStatus.delete(l);
  };
}

function assinarVersao(l: () => void) {
  ouvintesVersao.add(l);
  return () => {
    ouvintesVersao.delete(l);
  };
}

export function useStatusOffline(): StatusOffline {
  return useSyncExternalStore(assinarStatus, getStatus, getStatus);
}

/** Numero que muda a cada alteracao local; use como dependencia para recarregar dados. */
export function useVersaoLocal(): number {
  return useSyncExternalStore(assinarVersao, () => versao, () => versao);
}
