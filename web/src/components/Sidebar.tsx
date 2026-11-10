import React from 'react';
import { LogoFast } from './LogoFast';
import {
  LayoutDashboard,
  ClipboardList,
  Users,
  Wrench,
  Shield,
  Package,
  Sparkles,
  ChevronRight,
  LogOut,
} from 'lucide-react';

export type AdminTab = 'dashboard' | 'chamados' | 'clientes' | 'tecnicos' | 'modelos';

interface Props {
  activeTab: AdminTab;
  onSelectTab: (tab: AdminTab) => void;
  onOpenNovaOS: () => void;
  totalOS: number;
  totalEmAtendimento: number;
  onLogout?: () => void;
}

export const Sidebar: React.FC<Props> = ({
  activeTab,
  onSelectTab,
  onOpenNovaOS,
  totalOS,
  totalEmAtendimento,
  onLogout,
}) => {
  const menuItems = [
    {
      id: 'dashboard' as AdminTab,
      label: 'Painel de Controle',
      icon: LayoutDashboard,
      badge: null,
    },
    {
      id: 'chamados' as AdminTab,
      label: 'Ordens de Serviço',
      icon: ClipboardList,
      badge: totalOS,
    },
    {
      id: 'clientes' as AdminTab,
      label: 'Gestão de Clientes',
      icon: Users,
      badge: null,
    },
    {
      id: 'tecnicos' as AdminTab,
      label: 'Equipe de Técnicos',
      icon: Wrench,
      badge: null,
    },
    {
      id: 'modelos' as AdminTab,
      label: 'Modelos de equipamento',
      icon: Package,
      badge: null,
    },
  ];

  return (
    <aside className="w-64 bg-fast-navy text-white border-r border-white/10 flex flex-col justify-between shrink-0 min-h-screen select-none font-sans shadow-xl">
      <div>
        {/* Marca: logo oficial sobre a placa clara, como no cabeçalho do app */}
        <div className="p-5 border-b border-white/10">
          <LogoFast variante="placa" className="h-9" />
          <p className="text-[10px] text-white/70 font-medium tracking-wide mt-2.5">Gestão de Ordens de Serviço</p>
        </div>

        {/* Action Button */}
        <div className="p-4">
          <button
            onClick={onOpenNovaOS}
            className="w-full py-2.5 px-4 bg-white hover:bg-secondary text-accent font-black text-xs rounded-xl shadow-lg shadow-black/15 flex items-center justify-center gap-2 transition-all cursor-pointer group"
          >
            <Sparkles className="w-4 h-4 text-accent group-hover:rotate-12 transition-transform" />
            <span>+ Criar Nova OS</span>
          </button>
        </div>

        {/* Navigation Section */}
        <nav className="px-3 space-y-1.5 mt-1">
          <div className="px-3 py-1.5 text-[10px] font-bold text-white/60 uppercase tracking-wider">
            Menu Principal
          </div>

          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                  isActive
                    ? 'bg-white text-accent font-bold shadow-md shadow-black/10'
                    : 'text-white/85 hover:text-white hover:bg-white/10'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-accent' : 'text-white/70'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== null && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      isActive
                        ? 'bg-accent text-white'
                        : 'bg-white/15 text-white border border-white/20'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Footer Section */}
      <div className="p-4 border-t border-white/10 space-y-3 bg-black/15">
        <div className="bg-white/10 border border-white/15 rounded-xl p-3 backdrop-blur-xs">
          <div className="flex items-center justify-between text-[11px] font-semibold text-white/75 mb-1.5">
            <span>OS em Atendimento</span>
            <span className="text-white font-bold bg-white/20 px-2 py-0.5 rounded-full text-[10px]">{totalEmAtendimento} ativas</span>
          </div>
          <div className="w-full bg-black/30 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-fast-sky h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (totalEmAtendimento / (totalOS || 1)) * 100)}%` }}
            />
          </div>
        </div>

        {onLogout && (
          <button
            onClick={onLogout}
            className="w-full py-2 px-3 bg-white/10 hover:bg-destructive/30 text-white/85 hover:text-white border border-white/15 hover:border-destructive/60 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Encerrar Sessão</span>
          </button>
        )}

        <div className="text-center pt-1">
          <p className="text-[10px] text-white/60 flex items-center justify-center gap-1">
            <Shield className="w-3 h-3 text-white/60" /> FAST Gôndolas & Check-outs
          </p>
        </div>
      </div>
    </aside>
  );
};


