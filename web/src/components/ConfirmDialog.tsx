import React from 'react';
import { AlertTriangle, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  titulo: string;
  mensagem: React.ReactNode;
  aviso?: React.ReactNode;
  textoConfirmar: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}

export const ConfirmDialog: React.FC<Props> = ({ titulo, mensagem, aviso, textoConfirmar, onConfirm, onClose }) => {
  const { enviando, erro, executar } = useAcaoAssincrona();

  return (
    <ModalShell
      titulo={titulo}
      icone={<AlertTriangle className="w-5 h-5" />}
      tom="destructive"
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-md"
    >
      <div className="space-y-4 text-xs">
        <div className="text-foreground/90 leading-relaxed">{mensagem}</div>
        {aviso && (
          <div className="p-3 bg-warning/10 border border-warning/30 rounded-xl text-[11px] text-foreground">{aviso}</div>
        )}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-border">
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            className="px-4 py-2 bg-secondary hover:bg-muted text-foreground rounded-xl text-xs font-semibold cursor-pointer border border-border disabled:opacity-60"
          >
            Voltar
          </button>
          <button
            type="button"
            disabled={enviando}
            onClick={async () => {
              const ok = await executar(onConfirm);
              if (ok) onClose();
            }}
            className="px-4 py-2 bg-destructive hover:bg-destructive/90 text-white rounded-xl text-xs font-bold shadow-md cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {textoConfirmar}
          </button>
        </div>
      </div>
    </ModalShell>
  );
};
