import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { mensagemErro } from '../utils/os';

interface Props {
  idOs: number;
  idVisita: number;
  /** Chamado ao clicar na miniatura, com a URL `blob:` já carregada (para abrir no visualizador). */
  onAbrir: (urlBlob: string) => void;
}

/**
 * Assinatura do cliente. A imagem fica cifrada no servidor e a rota exige autenticação, então o painel a busca com o
 * token e a exibe por uma URL `blob:` (liberada ao desmontar, para não vazar memória nem deixar a imagem acessível).
 */
export const AssinaturaImagem: React.FC<Props> = ({ idOs, idVisita, onAbrir }) => {
  const [url, setUrl] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let criada: string | null = null;
    setUrl(null);
    setErro(null);
    apiClient
      .baixarAssinatura(idOs, idVisita)
      .then((blob) => {
        if (cancelado) return;
        criada = URL.createObjectURL(blob);
        setUrl(criada);
      })
      .catch((e) => {
        if (!cancelado) setErro(mensagemErro(e, 'Não foi possível carregar a assinatura.'));
      });
    return () => {
      cancelado = true;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [idOs, idVisita]);

  if (erro) return <p className="text-[11px] text-destructive max-w-[16rem]">{erro}</p>;
  if (!url) return <p className="text-[11px] text-muted-foreground">Carregando assinatura…</p>;
  return (
    <button
      type="button"
      onClick={() => onAbrir(url)}
      className="bg-secondary p-2.5 rounded-xl border border-border cursor-pointer"
    >
      <img src={url} alt="Assinatura do cliente" className="h-14 object-contain" />
    </button>
  );
};
