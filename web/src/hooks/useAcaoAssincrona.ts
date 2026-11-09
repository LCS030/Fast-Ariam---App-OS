import { useCallback, useRef, useState } from 'react';
import { mensagemErro } from '../utils/os';

/**
 * Executa uma ação assíncrona de formulário/modal controlando "enviando" (evita envio duplicado por clique repetido)
 * e exibindo a mensagem de erro do servidor (409/422/etc.) sem fechar o modal nem perder os dados digitados.
 */
export function useAcaoAssincrona() {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const emAndamento = useRef(false);

  const executar = useCallback(async (acao: () => Promise<void>): Promise<boolean> => {
    if (emAndamento.current) return false;
    emAndamento.current = true;
    setEnviando(true);
    setErro(null);
    try {
      await acao();
      return true;
    } catch (e) {
      setErro(mensagemErro(e));
      return false;
    } finally {
      emAndamento.current = false;
      setEnviando(false);
    }
  }, []);

  const limparErro = useCallback(() => setErro(null), []);

  return { enviando, erro, executar, limparErro, definirErro: setErro };
}
