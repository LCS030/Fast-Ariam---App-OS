import React, { useState, useEffect } from 'react';
import { OrdemServico, Tecnico } from '../types';
import { Wrench, UserCheck, Loader2 } from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';

interface Props {
  isOpen: boolean;
  os: OrdemServico | null;
  tecnicos: Tecnico[];
  onClose: () => void;
  /** Envia somente { id_tecnico_atribuido } à API; o status é definido pelo servidor. */
  onConfirm: (id_os: number, id_tecnico: number) => Promise<void>;
}

export const ModalAtribuirTecnico: React.FC<Props> = ({ isOpen, os, tecnicos, onClose, onConfirm }) => {
  const [selectedTecnicoId, setSelectedTecnicoId] = useState<number>(0);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  const idOs = os?.id_os;
  useEffect(() => {
    limparErro();
    setSelectedTecnicoId(os?.id_tecnico_atribuido || 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, idOs]);

  if (!isOpen || !os) return null;

  const elegiveis = tecnicos.filter((t) => t.is_active !== false && t.role !== 'admin');

  const handleSave = async () => {
    if (selectedTecnicoId <= 0) return;
    const ok = await executar(() => onConfirm(os.id_os, selectedTecnicoId));
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={`${os.id_tecnico_atribuido ? 'Reatribuir' : 'Atribuir'} técnico — OS #${os.codigo_os}`}
      subtitulo={`Cliente: ${os.cliente?.razao_social || os.cliente_nome || 'não informado'}`}
      icone={<Wrench className="w-5 h-5" />}
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-md"
    >
      <div className="space-y-3 mb-6">
        <p className="block text-xs font-semibold text-foreground">Selecione o técnico responsável:</p>
        <div className="space-y-2 max-h-60 overflow-y-auto pr-1" role="radiogroup" aria-label="Técnicos disponíveis">
          {elegiveis.length === 0 ? (
            <div className="p-6 text-center text-muted-foreground bg-secondary/40 rounded-xl border border-dashed border-border text-xs">
              Nenhum técnico ativo disponível para atribuição.
            </div>
          ) : (
            elegiveis.map((t) => {
              const isSelected = selectedTecnicoId === t.id_tecnico;
              return (
                <button
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  key={t.id_tecnico}
                  onClick={() => setSelectedTecnicoId(t.id_tecnico)}
                  className={`w-full text-left flex items-center justify-between p-3 rounded-2xl border transition-all cursor-pointer ${
                    isSelected
                      ? 'bg-primary/10 border-primary/50 ring-1 ring-primary/30'
                      : 'bg-secondary/60 border-border hover:border-muted-foreground/30'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-full bg-primary/20 text-primary-strong flex items-center justify-center font-bold text-xs ring-2 ring-border">
                      {t.nome.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <p className="text-xs font-bold text-foreground">{t.nome}</p>
                      <p className="text-[10px] text-muted-foreground">{t.email}</p>
                    </div>
                  </div>
                  {isSelected && <UserCheck className="w-5 h-5 text-primary-strong" />}
                </button>
              );
            })
          )}
        </div>
      </div>

      <div className="flex items-center justify-end gap-3 pt-3 border-t border-border text-xs">
        <button
          type="button"
          onClick={onClose}
          disabled={enviando}
          className="px-4 py-2 bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground rounded-xl font-semibold cursor-pointer disabled:opacity-60"
        >
          Cancelar
        </button>
        <button
          type="button"
          disabled={enviando || selectedTecnicoId <= 0 || selectedTecnicoId === os.id_tecnico_atribuido}
          onClick={handleSave}
          className="px-5 py-2 bg-primary hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed text-primary-foreground font-bold rounded-xl shadow-md shadow-primary/20 cursor-pointer flex items-center gap-2"
        >
          {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
          Confirmar atribuição
        </button>
      </div>
    </ModalShell>
  );
};
