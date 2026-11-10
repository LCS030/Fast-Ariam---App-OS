import React, { useState, useEffect } from 'react';
import { XCircle, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

const MAX_MOTIVO = 500;

interface Props {
  isOpen: boolean;
  codigoOS: string;
  onClose: () => void;
  onConfirm: (motivo: string) => Promise<void>;
}

/** Cancelamento com motivo obrigatório (RF-11 / RN-12). Usa POST /cancelar; o 409 do servidor é exibido no modal. */
export const ModalCancelarOS: React.FC<Props> = ({ isOpen, codigoOS, onClose, onConfirm }) => {
  const [motivo, setMotivo] = useState('');
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  useEffect(() => {
    if (isOpen) {
      setMotivo('');
      setErroLocal(null);
      limparErro();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!motivo.trim()) return setErroLocal('Informe o motivo do cancelamento.');
    setErroLocal(null);
    const ok = await executar(() => onConfirm(motivo.trim()));
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={`Cancelar OS #${codigoOS}`}
      subtitulo="O cancelamento é lógico: o histórico é mantido e as pausas ativas são encerradas"
      icone={<XCircle className="w-5 h-5" />}
      tom="destructive"
      onClose={onClose}
      erro={erro}
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {erroLocal && (
          <div role="alert" className="p-3 bg-destructive/10 border border-destructive/30 rounded-xl text-destructive font-semibold">
            {erroLocal}
          </div>
        )}
        <div>
          <label htmlFor="cancel-motivo" className="block font-semibold text-foreground mb-1">
            Motivo do cancelamento *
          </label>
          <textarea
            id="cancel-motivo"
            rows={4}
            maxLength={MAX_MOTIVO}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ex.: cliente desmarcou o atendimento"
            className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-destructive focus:outline-none"
          />
          <p className="text-[11px] text-muted-foreground mt-1 text-right">
            {motivo.length}/{MAX_MOTIVO}
          </p>
        </div>
        <p className="text-[11px] text-muted-foreground">
          OS finalizada ou já cancelada não pode ser cancelada; nesse caso o servidor recusa a operação.
        </p>
        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground bg-secondary hover:bg-muted cursor-pointer disabled:opacity-60"
          >
            Voltar
          </button>
          <button
            type="submit"
            disabled={enviando}
            className="px-5 py-2 rounded-xl text-xs font-bold text-white bg-destructive hover:bg-destructive/90 shadow-md cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            Confirmar cancelamento
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
