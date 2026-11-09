import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { mensagemErro } from '../utils/os';

interface Props {
  idOs: number;
  /** Referência da foto como veio da API (`/static/uploads/...`): é só um identificador, não um endereço público. */
  url: string;
  alt: string;
  className?: string;
}

/**
 * Foto de OS. As fotos ficam em armazenamento PRIVADO e só saem por GET /api/chamados/{id}/arquivos/conteudo, que exige
 * login e confere se a foto é mesmo daquela OS. Como `<img src>` não envia `Authorization`, busca-se o arquivo com o
 * token e exibe-se por uma URL `blob:`, liberada ao desmontar (não deixa a imagem acessível nem vaza memória).
 */
export const FotoSegura: React.FC<Props> = ({ idOs, url, alt, className }) => {
  const [src, setSrc] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let criada: string | null = null;
    setSrc(null);
    setErro(null);
    apiClient
      .baixarArquivo(idOs, url)
      .then((blob) => {
        if (cancelado) return;
        criada = URL.createObjectURL(blob);
        setSrc(criada);
      })
      .catch((e) => {
        if (!cancelado) setErro(mensagemErro(e, 'Não foi possível carregar a foto.'));
      });
    return () => {
      cancelado = true;
      if (criada) URL.revokeObjectURL(criada);
    };
  }, [idOs, url]);

  if (erro) {
    return (
      <span role="alert" className="flex items-center justify-center w-full h-full p-2 text-[10px] text-center text-destructive">
        {erro}
      </span>
    );
  }
  if (!src) {
    return (
      <span className="flex items-center justify-center w-full h-full text-[10px] text-muted-foreground animate-pulse">
        Carregando…
      </span>
    );
  }
  return <img src={src} alt={alt} className={className} />;
};
