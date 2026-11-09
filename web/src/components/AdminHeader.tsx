import React from 'react';
import { Plus, LogOut, Server, RefreshCw } from 'lucide-react';

interface Props {
  activeTabTitle: string;
  totalChamados: number;
  totalFinalizadas: number;
  /** Resultado da última carga: true = API respondeu; false = falha de conexão; null = ainda não carregou. */
  apiOnline: boolean | null;
  carregando: boolean;
  onRefresh: () => void;
  onOpenNovaOS: () => void;
  onLogout?: () => void;
}

export const AdminHeader: React.FC<Props> = ({
  activeTabTitle,
  totalChamados,
  totalFinalizadas,
  apiOnline,
  carregando,
  onRefresh,
  onOpenNovaOS,
  onLogout,
}) => {
  return (
    <header className="bg-[#003875] border-b border-blue-900/60 sticky top-0 z-30 px-6 py-4 text-white shadow-md">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-black text-white font-['Space_Grotesk'] tracking-tight flex items-center gap-2">
            <span>{activeTabTitle}</span>
          </h1>
          <p className="text-xs text-blue-200 mt-0.5 font-medium">
            Gestão Integrada de Ordens de Serviço — FAST Gôndolas & Check-outs
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <button
            onClick={onRefresh}
            disabled={carregando}
            title="Estado da última consulta à API. Clique para atualizar os dados."
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl border text-xs font-semibold transition-all cursor-pointer disabled:opacity-70 ${
              apiOnline === true
                ? 'bg-emerald-500/20 text-emerald-200 border-emerald-400/40 hover:bg-emerald-500/30'
                : apiOnline === false
                ? 'bg-amber-500/20 text-amber-200 border-amber-400/40 hover:bg-amber-500/30'
                : 'bg-white/10 text-blue-200 border-white/20 hover:bg-white/20'
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                apiOnline === true ? 'bg-emerald-400' : apiOnline === false ? 'bg-amber-400' : 'bg-blue-300'
              }`}
            />
            <Server className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">
              {apiOnline === true ? 'API conectada' : apiOnline === false ? 'API indisponível' : 'Verificando API'}
            </span>
            <RefreshCw className={`w-3 h-3 text-white/80 ${carregando ? 'animate-spin' : ''}`} />
          </button>

          <div className="hidden sm:flex items-center gap-3 bg-white/10 px-3.5 py-1.5 rounded-xl border border-white/20 text-xs backdrop-blur-xs">
            <div>
              <span className="text-blue-200 text-[10px] block font-medium">Total OS</span>
              <span className="font-bold text-white">{totalChamados}</span>
            </div>
            <div className="h-5 w-px bg-white/20" />
            <div>
              <span className="text-blue-200 text-[10px] block font-medium">Finalizadas</span>
              <span className="font-bold text-emerald-300">{totalFinalizadas}</span>
            </div>
          </div>

          <button
            onClick={onOpenNovaOS}
            className="px-4 py-2 bg-white hover:bg-blue-50 text-[#003875] font-black text-xs rounded-xl shadow-md shadow-black/20 flex items-center gap-1.5 transition-all cursor-pointer group"
          >
            <Plus className="w-4 h-4 text-[#003875] group-hover:rotate-90 transition-transform" />
            <span>Nova OS</span>
          </button>

          {onLogout && (
            <button
              onClick={onLogout}
              title="Sair do sistema"
              aria-label="Sair do sistema"
              className="p-2 bg-white/10 hover:bg-red-500/25 text-white hover:text-red-200 rounded-xl border border-white/20 text-xs font-semibold flex items-center gap-1 transition-all cursor-pointer"
            >
              <LogOut className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </header>
  );
};
