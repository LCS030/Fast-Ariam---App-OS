import React from 'react';
import logoFast from '../assets/fast_logo.png';

interface Props {
  /**
   * `plana`: a logo direto sobre fundo claro (ex.: tela de login).
   * `placa`: sobre fundo escuro (marinho), dentro da placa clara de cantos em diagonal do cabeçalho do app mobile.
   */
  variante?: 'plana' | 'placa';
  /** Classes da <img> (controle a altura aqui; a largura acompanha a proporção). */
  className?: string;
}

/** Logo oficial da FAST Gôndolas & Check-outs: o mesmo arquivo usado no aplicativo mobile. */
export const LogoFast: React.FC<Props> = ({ variante = 'plana', className = 'h-10' }) => {
  const imagem = (
    <img
      src={logoFast}
      alt="FAST Gôndolas & Check-outs"
      width={819}
      height={232}
      draggable={false}
      className={`w-auto select-none ${className}`}
    />
  );
  if (variante === 'placa') {
    return (
      <div className="inline-flex bg-secondary rounded-tl-[20px] rounded-br-[20px] px-3.5 py-2 shadow-md shadow-black/20">
        {imagem}
      </div>
    );
  }
  return imagem;
};
