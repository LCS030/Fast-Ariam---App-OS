// Recalcula o que o indicador global mostra (fila + sessao) e avisa as telas.
import { contarFila } from "./outbox";
import { avaliarSessao } from "./sessao";
import { atualizarStatus, notificarMudancaLocal } from "./store";

export async function atualizarContagens(): Promise<void> {
  try {
    const av = await avaliarSessao();
    const c = av.sessao
      ? await contarFila(av.sessao.idTecnico)
      : { pendentes: 0, rejeitadas: 0, arquivosPendentes: 0 };
    atualizarStatus({ ...c, situacaoSessao: av.situacao });
  } catch {
    // banco indisponivel neste instante: mantem os valores anteriores
  }
  notificarMudancaLocal();
}
