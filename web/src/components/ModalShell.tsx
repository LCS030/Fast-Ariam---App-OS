import React from 'react';
import { X, AlertCircle } from 'lucide-react';

interface Props {
  titulo: string;
  subtitulo?: string;
  icone: React.ReactNode;
  tom?: 'primary' | 'destructive' | 'warning';
  onClose: () => void;
  erro?: string | null;
  larguraMax?: string;
  children: React.ReactNode;
}

const TONS = {
  primary: 'bg-primary/10 border-primary/20 text-primary-strong',
  destructive: 'bg-destructive/10 border-destructive/30 text-destructive',
  warning: 'bg-amber-500/10 border-amber-500/30 text-amber-600',
};

/** Moldura padrão dos modais do painel (mesmo visual dos demais modais). */
export const ModalShell: React.FC<Props> = ({
  titulo,
  subtitulo,
  icone,
  tom = 'primary',
  onClose,
  erro,
  larguraMax = 'max-w-lg',
  children,
}) => (
  <div
    className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4 overflow-y-auto font-sans"
    role="dialog"
    aria-modal="true"
    aria-label={titulo}
  >
    <div className={`w-full ${larguraMax} bg-card border border-border rounded-3xl p-6 shadow-2xl relative my-8 text-foreground`}>
      <div className="flex items-start justify-between border-b border-border pb-4 mb-4 gap-3">
        <div className="flex items-center gap-3">
          <div className={`p-2.5 border rounded-2xl ${TONS[tom]}`}>{icone}</div>
          <div>
            <h2 className="text-lg font-bold text-foreground font-['Space_Grotesk']">{titulo}</h2>
            {subtitulo && <p className="text-xs text-muted-foreground">{subtitulo}</p>}
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Fechar"
          className="p-2 text-muted-foreground hover:text-foreground hover:bg-secondary rounded-xl transition-all cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {erro && (
        <div
          role="alert"
          className="mb-4 p-3 bg-destructive/10 border border-destructive/30 rounded-xl text-destructive text-xs font-semibold flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{erro}</span>
        </div>
      )}

      {children}
    </div>
  </div>
);
