import React, { useState, useEffect } from 'react';
import { MOTIVOS_PAUSA, MotivoPausa } from '../types';
import { PauseCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  isOpen: boolean;
  codigoOS: string;
  onClose: () => void;
  onConfirm: (motivo: MotivoPausa, descricao?: string) => Promise<void>;
}

/** Pausa da OS pelo administrador (RN-30). Lista oficial de motivos (RN-29); "Outro" exige descrição. */
export const ModalPausa: React.FC<Props> = ({ isOpen, codigoOS, onClose, onConfirm }) => {
  const [motivo, setMotivo] = useState<MotivoPausa | ''>('');
  const [descricao, setDescricao] = useState('');
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  useEffect(() => {
    if (isOpen) {
      setMotivo('');
      setDescricao('');
      setErroLocal(null);
      limparErro();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!motivo) return setErroLocal('Selecione o motivo da pausa.');
    if (motivo === 'Outro' && !descricao.trim()) {
      return setErroLocal('Para o motivo "Outro", a descrição é obrigatória.');
    }
    setErroLocal(null);
    const ok = await executar(() => onConfirm(motivo, descricao.trim() || undefined));
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={`Pausar OS #${codigoOS}`}
      subtitulo="Selecione o motivo da interrupção do atendimento"
      icone={<PauseCircle className="w-5 h-5" />}
      tom="warning"
      onClose={onClose}
      erro={erro}
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {erroLocal && (
          <div role="alert" className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-600 dark:text-red-400 text-xs font-semibold">
            {erroLocal}
          </div>
        )}

        <fieldset>
          <legend className="block text-xs font-semibold text-foreground mb-2">Motivo da pausa *</legend>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {MOTIVOS_PAUSA.map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={motivo === m}
                onClick={() => setMotivo(m)}
                className={`text-left text-xs p-3 rounded-xl border transition-all cursor-pointer ${
                  motivo === m
                    ? 'bg-amber-500/15 border-amber-500/50 text-amber-700 font-semibold ring-1 ring-amber-500/30'
                    : 'bg-secondary/60 border-border text-foreground hover:border-accent/40'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </fieldset>

        <div>
          <label htmlFor="pausa-desc" className="block text-xs font-semibold text-foreground mb-1">
            Descrição {motivo === 'Outro' ? '*' : '(opcional)'}
          </label>
          <textarea
            id="pausa-desc"
            rows={3}
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
            className="w-full bg-secondary border border-border rounded-xl p-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-amber-500 focus:outline-none focus:ring-1 focus:ring-amber-500"
          />
        </div>

        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-start gap-2 text-xs text-amber-800">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
          <span>
            A OS ficará <strong>Pausada</strong> e o registro guardará que a pausa foi feita pelo administrador. Não há retomada: o
            técnico deve finalizar o deslocamento de volta; então a OS passa para <strong>Aguardando Reagendamento</strong> e você
            poderá agendar a nova visita.
          </span>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            className="px-4 py-2 rounded-xl text-xs font-semibold text-muted-foreground hover:text-foreground bg-secondary hover:bg-muted transition-colors cursor-pointer disabled:opacity-60"
          >
            Voltar
          </button>
          <button
            type="submit"
            disabled={enviando}
            className="px-5 py-2 rounded-xl text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 shadow-md shadow-amber-600/20 transition-all cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            Confirmar pausa
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
