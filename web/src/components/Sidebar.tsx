import React from 'react';
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
    <aside className="w-64 bg-gradient-to-b from-[#003875] via-[#003066] to-[#00224A] text-white border-r border-blue-900/50 flex flex-col justify-between shrink-0 min-h-screen select-none font-sans shadow-xl">
      <div>
        {/* Brand Header */}
        <div className="p-5 border-b border-white/10 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-2xl bg-white flex items-center justify-center text-[#003875] font-black shadow-md ring-2 ring-white/30">
              <Wrench className="w-5 h-5 text-[#003875]" />
            </div>
            <div>
              <h1 className="text-base font-black text-white font-['Space_Grotesk'] tracking-tight flex items-center gap-1.5">
                <span className="text-white font-black">FAST</span> <span className="text-red-400 font-black">GÔNDOLAS</span>
              </h1>
              <p className="text-[10px] text-blue-200 font-medium tracking-wide">
                Gôndolas & Check-outs • OS
              </p>
            </div>
          </div>
        </div>

        {/* Action Button */}
        <div className="p-4">
          <button
            onClick={onOpenNovaOS}
            className="w-full py-2.5 px-4 bg-white hover:bg-blue-50 text-[#003875] font-black text-xs rounded-xl shadow-lg shadow-black/15 flex items-center justify-center gap-2 transition-all cursor-pointer group"
          >
            <Sparkles className="w-4 h-4 text-[#003875] group-hover:rotate-12 transition-transform" />
            <span>+ Criar Nova OS</span>
          </button>
        </div>

        {/* Navigation Section */}
        <nav className="px-3 space-y-1.5 mt-1">
          <div className="px-3 py-1.5 text-[10px] font-bold text-blue-200/75 uppercase tracking-wider">
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
                    ? 'bg-white text-[#003875] font-bold shadow-md shadow-black/10'
                    : 'text-blue-100 hover:text-white hover:bg-white/10'
                }`}
              >
                <div className="flex items-center gap-3">
                  <Icon className={`w-4 h-4 ${isActive ? 'text-[#003875]' : 'text-blue-200'}`} />
                  <span>{item.label}</span>
                </div>
                {item.badge !== null && (
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      isActive
                        ? 'bg-[#003875] text-white'
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
          <div className="flex items-center justify-between text-[11px] font-semibold text-blue-200 mb-1.5">
            <span>OS em Atendimento</span>
            <span className="text-white font-bold bg-white/20 px-2 py-0.5 rounded-full text-[10px]">{totalEmAtendimento} ativas</span>
          </div>
          <div className="w-full bg-black/30 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-blue-300 h-full rounded-full transition-all duration-500"
              style={{ width: `${Math.min(100, (totalEmAtendimento / (totalOS || 1)) * 100)}%` }}
            />
          </div>
        </div>

        {onLogout && (
          <button
            onClick={onLogout}
            className="w-full py-2 px-3 bg-white/10 hover:bg-red-500/20 text-blue-100 hover:text-red-200 border border-white/15 hover:border-red-400/40 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition-all cursor-pointer"
          >
            <LogOut className="w-3.5 h-3.5" />
            <span>Encerrar Sessão</span>
          </button>
        )}

        <div className="text-center pt-1">
          <p className="text-[10px] text-blue-200/70 flex items-center justify-center gap-1">
            <Shield className="w-3 h-3 text-blue-300" /> FAST Gôndolas & Check-outs
          </p>
        </div>
      </div>
    </aside>
  );
};


