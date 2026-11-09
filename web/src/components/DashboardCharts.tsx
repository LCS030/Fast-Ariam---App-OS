import React, { useState } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from 'recharts';
import { OrdemServico, STATUS_OS, StatusChamado, Tecnico } from '../types';
import { Filter, PieChart as PieIcon, BarChart2 } from 'lucide-react';

interface Props {
  /** OS não canceladas (já filtradas por período). */
  ativas: OrdemServico[];
  /** OS canceladas (já filtradas por período). */
  canceladas: OrdemServico[];
  tecnicos: Tecnico[];
}

type FiltroGrafico = StatusChamado | 'TODOS' | 'CANCELADAS';

// Cores da marca FAST para os gráficos (mantidas do painel anterior).
const COR_STATUS: Record<StatusChamado | 'Cancelada', string> = {
  Pendente: '#D97706',
  Agendado: '#004F9F',
  'Em Atendimento': '#2563EB',
  Pausado: '#F59E0B',
  'Aguardando Reagendamento': '#7C3AED',
  Finalizado: '#16A34A',
  Cancelada: '#DC2626',
};

const STATUS_EM_ABERTO: StatusChamado[] = ['Pendente', 'Agendado', 'Em Atendimento', 'Pausado', 'Aguardando Reagendamento'];

const TOOLTIP_STYLE = {
  backgroundColor: 'var(--color-card)',
  borderColor: 'var(--color-border)',
  borderRadius: '0.75rem',
  color: 'var(--color-foreground)',
  fontSize: '12px',
};

export const DashboardCharts: React.FC<Props> = ({ ativas, canceladas, tecnicos }) => {
  const [filtro, setFiltro] = useState<FiltroGrafico>('TODOS');

  const consideradas: OrdemServico[] =
    filtro === 'TODOS'
      ? [...ativas, ...canceladas]
      : filtro === 'CANCELADAS'
      ? canceladas
      : ativas.filter((c) => c.status === filtro);

  const statusData = [
    ...STATUS_OS.map((s) => ({
      name: s,
      value: filtro === 'TODOS' || filtro === s ? ativas.filter((c) => c.status === s).length : 0,
      color: COR_STATUS[s],
    })),
    {
      name: 'Cancelada',
      value: filtro === 'TODOS' || filtro === 'CANCELADAS' ? canceladas.length : 0,
      color: COR_STATUS.Cancelada,
    },
  ].filter((d) => d.value > 0);

  const tecnicoWorkloadData = tecnicos.map((tec) => {
    const dele = consideradas.filter((c) => c.id_tecnico_atribuido === tec.id_tecnico && !c.is_cancelled);
    const partes = tec.nome.split(' ');
    return {
      nome: partes[0] + (partes[1] ? ` ${partes[1][0]}.` : ''),
      'Em aberto': dele.filter((c) => STATUS_EM_ABERTO.includes(c.status)).length,
      Finalizadas: dele.filter((c) => c.status === 'Finalizado').length,
    };
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-card border border-border p-3.5 rounded-2xl shadow-sm">
        <div className="flex items-center gap-2">
          <Filter className="w-4 h-4 text-accent" />
          <span className="text-xs font-bold text-foreground">Filtro exclusivo de gráficos (status):</span>
          <span className="text-[11px] text-muted-foreground">{consideradas.length} OS consideradas nos gráficos</span>
        </div>

        <select
          aria-label="Filtrar gráficos por status"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value as FiltroGrafico)}
          className="bg-secondary border border-border rounded-xl px-3 py-1.5 text-xs font-semibold text-foreground focus:border-accent focus:outline-none cursor-pointer"
        >
          <option value="TODOS">Todos os status nos gráficos</option>
          {STATUS_OS.map((s) => (
            <option key={s} value={s}>
              Somente {s}
            </option>
          ))}
          <option value="CANCELADAS">Somente canceladas</option>
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="surface-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-accent/10 rounded-xl border border-accent/20 text-accent">
                <PieIcon className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground font-['Space_Grotesk']">Distribuição por status</h3>
                <p className="text-xs text-muted-foreground">Volume de ordens de serviço por etapa operacional</p>
              </div>
            </div>
            <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-secondary text-accent border border-border">
              {consideradas.length} OS
            </span>
          </div>

          <div className="h-64 w-full flex items-center justify-center">
            {statusData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={statusData} cx="50%" cy="50%" innerRadius={58} outerRadius={84} paddingAngle={4} dataKey="value">
                    {statusData.map((entry) => (
                      <Cell key={entry.name} fill={entry.color} stroke="transparent" strokeWidth={2} />
                    ))}
                  </Pie>
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend
                    verticalAlign="bottom"
                    align="center"
                    iconType="circle"
                    formatter={(value) => <span className="text-foreground/80 text-xs">{value}</span>}
                  />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-muted-foreground text-xs">Sem ordens de serviço para exibir no período/filtro.</div>
            )}
          </div>
        </div>

        <div className="surface-card p-5">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-primary/10 rounded-xl border border-primary/20 text-primary">
                <BarChart2 className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground font-['Space_Grotesk']">Ordens por técnico</h3>
                <p className="text-xs text-muted-foreground">Distribuição de chamados na equipe de campo</p>
              </div>
            </div>
          </div>

          <div className="h-64 w-full flex items-center justify-center">
            {tecnicoWorkloadData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={tecnicoWorkloadData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis dataKey="nome" stroke="#888888" fontSize={11} tickLine={false} />
                  <YAxis stroke="#888888" fontSize={11} tickLine={false} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP_STYLE} />
                  <Legend
                    verticalAlign="top"
                    align="right"
                    iconType="square"
                    formatter={(value) => <span className="text-foreground/80 text-xs">{value}</span>}
                  />
                  <Bar dataKey="Em aberto" fill="#004F9F" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="Finalizadas" fill="#16A34A" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-muted-foreground text-xs">Nenhum técnico disponível para exibir.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
