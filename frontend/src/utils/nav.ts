import type { Router } from "expo-router";

/**
 * Volta para o detalhe da OS depois de uma acao concluida. As telas de acao sao empilhadas
 * a partir do detalhe, entao voltar evita acumular copias da tela na pilha; o detalhe
 * recarrega os dados ao ganhar foco. Sem historico (ex.: link direto), abre a OS.
 */
export function voltarParaOS(router: Router, chamadoId: number | string): void {
  if (router.canGoBack()) {
    router.back();
  } else {
    router.replace({ pathname: "/detalheChamado/[id]", params: { id: String(chamadoId) } });
  }
}

/**
 * Abre a tela de pendencias/rejeicoes. As rotas tipadas do expo-router so passam a conhecer a
 * rota nova depois que `expo start` regenera .expo/types; o cast evita depender disso.
 */
export function irParaPendencias(router: Router): void {
  router.push("/Pendencias/indexPendencias" as never);
}
