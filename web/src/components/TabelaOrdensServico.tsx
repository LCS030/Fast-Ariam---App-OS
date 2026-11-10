import React, { useState } from 'react';
import { OrdemServico, STATUS_OS, StatusChamado } from '../types';
import { StatusBadge } from './StatusBadge';
import { formatData, permissaoAtribuir, osTerminal } from '../utils/os';
import { Search, Eye, Edit2, UserCheck, Building, Clock, ShieldCheck, Sparkles, Loader2, AlertTriangle } from 'lucide-react';

interface Props {
  /** OS não canceladas. */
  ativas: OrdemServico[];
  /** OS canceladas (is_cancelled = true). */
  canceladas: OrdemServico[];
  carregando?: boolean;
  /** Verdadeiro quando a listagem falhou: a tabela mostra "indisponível" em vez de "vazio". */
  erroCarregamento?: boolean;
  onSelectOS: (os: OrdemServico) => void;
  onEditOS: (os: OrdemServico) => void;
  onAssignTecnico: (os: OrdemServico) => void;
  onOpenNovaOS: () => void;
}

type FiltroStatus = StatusChamado | 'TODOS' | 'CANCELADAS';

export const TabelaOrdensServico: React.FC<Props> = ({
  ativas,
  canceladas,
  carregando = false,
  erroCarregamento = false,
  onSelectOS,
  onEditOS,
  onAssignTecnico,
  onOpenNovaOS,
}) => {
  const [filterStatus, setFilterStatus] = useState<FiltroStatus>('TODOS');
  const [searchQuery, setSearchQuery] = useState('');

  const base =
    filterStatus === 'CANCELADAS'
      ? canceladas
      : filterStatus === 'TODOS'
      ? ativas
      : ativas.filter((item) => item.status === filterStatus);

  const q = searchQuery.toLowerCase().trim();
  const filtered = q
    ? base.filter((item) =>
        [
          item.codigo_os,
          item.cliente.razao_social,
          item.cliente_nome,
          item.cliente.cidade,
          item.tecnico?.nome,
          item.descricao_cliente,
          item.pedido,
        ].some((campo) => (campo || '').toLowerCase().includes(q))
      )
    : base;

  const totalBase = filterStatus === 'CANCELADAS' ? canceladas.length : ativas.length;

  return (
    <div className="surface-card p-5 space-y-4">
      <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-extrabold text-foreground font-['Space_Grotesk'] tracking-tight">
            Gestão Geral de Ordens de Serviço
          </h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            Exibindo <strong className="text-accent">{filtered.length}</strong> de {totalBase} ordens de serviço
            {filterStatus === 'CANCELADAS' ? ' canceladas' : ''}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
            <input
              type="text"
              aria-label="Buscar ordens de serviço"
              placeholder="Buscar código, cliente, cidade ou técnico..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-secondary border border-border rounded-xl py-2 pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
            />
          </div>

          <select
            aria-label="Filtrar por status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value as FiltroStatus)}
            className="bg-secondary border border-border rounded-xl px-3 py-2 text-xs text-foreground focus:border-accent focus:outline-none cursor-pointer"
          >
            <option value="TODOS">Todos os Status</option>
            {STATUS_OS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
            <option value="CANCELADAS">Canceladas</option>
          </select>

          <button
            onClick={onOpenNovaOS}
            className="py-2 px-3.5 bg-primary hover:bg-primary/90 text-primary-foreground font-bold text-xs rounded-xl shadow-md shadow-primary/20 flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>+ Nova OS</span>
          </button>
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-border bg-secondary/80 text-muted-foreground font-semibold uppercase text-[10px] tracking-wider">
              <th className="py-3 px-4">Código / Status</th>
              <th className="py-3 px-4">Cliente / Localização</th>
              <th className="py-3 px-4">Técnico Responsável</th>
              <th className="py-3 px-4">Data de Agendamento</th>
              <th className="py-3 px-4">Garantia</th>
              <th className="py-3 px-4 text-right">Ações</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {carregando && filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-muted-foreground">
                  <span className="inline-flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" /> Carregando ordens de serviço...
                  </span>
                </td>
              </tr>
            ) : erroCarregamento && filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-destructive">
                  <span className="inline-flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Não foi possível carregar as ordens de serviço. Use "Tentar novamente".
                  </span>
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-8 text-muted-foreground">
                  Nenhuma ordem de serviço encontrada com os filtros selecionados.
                </td>
              </tr>
            ) : (
              filtered.map((item) => {
                const tec = item.tecnico;
                const podeAtribuir = permissaoAtribuir(item).permitido;
                const editavel = !osTerminal(item);
                return (
                  <tr key={item.id_os} className="hover:bg-muted/50 transition-colors group">
                    <td className="py-3.5 px-4 font-medium">
                      <div className="flex flex-col gap-1">
                        <span className="font-extrabold text-foreground font-['Space_Grotesk'] text-xs group-hover:text-primary-strong transition-colors">
                          #{item.codigo_os}
                        </span>
                        <StatusBadge status={item.status} cancelada={item.is_cancelled} size="sm" />
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <p className="font-bold text-foreground flex items-center gap-1.5">
                        <Building className="w-3.5 h-3.5 text-primary-strong shrink-0" />
                        <span>{item.cliente.razao_social}</span>
                      </p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {item.cliente.cidade ? `${item.cliente.cidade}/${item.cliente.uf}` : 'Localização não informada'}
                        {item.cliente.contato_principal_nome ? ` • Contato: ${item.cliente.contato_principal_nome}` : ''}
                      </p>
                    </td>

                    <td className="py-3.5 px-4">
                      {tec ? (
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-primary-strong text-[10px] shrink-0">
                            {tec.nome.slice(0, 2).toUpperCase()}
                          </div>
                          <div className="min-w-0">
                            <p className="font-bold text-foreground text-xs truncate">{tec.nome}</p>
                            <p className="text-[10px] text-muted-foreground truncate">{tec.email}</p>
                          </div>
                        </div>
                      ) : item.id_tecnico_atribuido ? (
                        <span className="text-muted-foreground">Técnico #{item.id_tecnico_atribuido}</span>
                      ) : podeAtribuir ? (
                        <button
                          onClick={() => onAssignTecnico(item)}
                          className="px-2.5 py-1 bg-primary/10 hover:bg-primary/20 text-primary-strong rounded-lg text-[11px] font-semibold border border-primary/30 flex items-center gap-1 cursor-pointer"
                        >
                          <UserCheck className="w-3 h-3" /> Atribuir
                        </button>
                      ) : (
                        <span className="text-muted-foreground">Sem técnico</span>
                      )}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-1.5 text-foreground/90 font-medium">
                        <Clock className="w-3.5 h-3.5 text-muted-foreground shrink-0" />
                        <span>{item.data_agendamento ? formatData(item.data_agendamento) : 'Não agendado'}</span>
                      </div>
                    </td>

                    <td className="py-3.5 px-4">
                      <span
                        className={`text-[11px] font-semibold flex items-center gap-1 ${
                          item.em_garantia ? 'text-success-strong' : 'text-muted-foreground'
                        }`}
                      >
                        <ShieldCheck className="w-3.5 h-3.5" />
                        {item.em_garantia ? 'Em Garantia' : 'Fora da garantia'}
                      </span>
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          title="Visualizar detalhes da OS"
                          onClick={() => onSelectOS(item)}
                          className="px-2.5 py-1.5 bg-primary/10 hover:bg-primary/20 text-primary-strong rounded-lg border border-primary/30 transition-colors cursor-pointer flex items-center gap-1 text-xs font-semibold"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          <span>Detalhes</span>
                        </button>

                        {podeAtribuir && (
                          <button
                            title={item.id_tecnico_atribuido ? 'Reatribuir técnico' : 'Atribuir técnico'}
                            aria-label={item.id_tecnico_atribuido ? 'Reatribuir técnico' : 'Atribuir técnico'}
                            onClick={() => onAssignTecnico(item)}
                            className="p-1.5 bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border transition-colors cursor-pointer"
                          >
                            <UserCheck className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {editavel && (
                          <button
                            title="Editar OS"
                            aria-label="Editar OS"
                            onClick={() => onEditOS(item)}
                            className="p-1.5 bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground rounded-lg border border-border transition-colors cursor-pointer"
                          >
                            <Edit2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
