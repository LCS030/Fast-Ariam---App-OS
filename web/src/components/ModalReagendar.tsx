import React, { useState, useEffect } from 'react';
import { CalendarClock, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';
import { hojeISO } from '../utils/os';
import { StatusChamado } from '../types';

interface Props {
  isOpen: boolean;
  codigoOS: string;
  status: StatusChamado;
  onClose: () => void;
  onConfirm: (dataVisita: string) => Promise<void>;
}

/**
 * Reagendamento (RF-13 / RN-14). A tela só é aberta nos status permitidos; o servidor continua sendo a fonte
 * de verdade e qualquer 409 (ex.: ida já iniciada) é exibido aqui.
 */
export const ModalReagendar: React.FC<Props> = ({ isOpen, codigoOS, status, onClose, onConfirm }) => {
  const [data, setData] = useState('');
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  useEffect(() => {
    if (isOpen) {
      setData('');
      setErroLocal(null);
      limparErro();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!data) return setErroLocal('Informe a nova data da visita.');
    if (data < hojeISO()) return setErroLocal('A nova data não pode estar no passado.');
    setErroLocal(null);
    const ok = await executar(() => onConfirm(data));
    if (ok) onClose();
  };

  const explicacao =
    status === 'Aguardando Reagendamento'
      ? 'Será criada uma nova visita, a pausa será encerrada e a OS voltará para "Agendado".'
      : 'A data da visita já existente será alterada (nenhuma visita nova é criada). Só é possível antes de o técnico iniciar o deslocamento de ida.';

  return (
    <ModalShell
      titulo={`Reagendar OS #${codigoOS}`}
      subtitulo={`Status atual: ${status}`}
      icone={<CalendarClock className="w-5 h-5" />}
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-md"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {erroLocal && (
          <div role="alert" className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-600 dark:text-red-400 font-semibold">
            {erroLocal}
          </div>
        )}
        <p className="text-muted-foreground leading-relaxed">{explicacao}</p>
        <div>
          <label htmlFor="reag-data" className="block font-semibold text-foreground mb-1">
            Nova data da visita *
          </label>
          <input
            id="reag-data"
            type="date"
            min={hojeISO()}
            value={data}
            onChange={(e) => setData(e.target.value)}
            className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none"
          />
        </div>
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
            className="px-5 py-2 rounded-xl text-xs font-bold text-primary-foreground bg-primary hover:bg-primary/90 shadow-md shadow-primary/20 cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            Confirmar reagendamento
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
