import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { OrdemServico, Cliente, Tecnico, STATUS_OS } from '../types';
import { ChamadoService } from '../services/chamadoService';
import { ApiError, TecnicoPayload } from '../services/apiClient';
import { Sidebar, AdminTab } from '../components/Sidebar';
import { AdminHeader } from '../components/AdminHeader';
import { DashboardCharts } from '../components/DashboardCharts';
import { TabelaOrdensServico } from '../components/TabelaOrdensServico';
import { ModalNovaOS, DadosFormOS } from '../components/ModalNovaOS';
import { ModalAtribuirTecnico } from '../components/ModalAtribuirTecnico';
import { ModalCliente } from '../components/ModalCliente';
import { ModalTecnico } from '../components/ModalTecnico';
import { ModalDetalheOSAdmin } from '../components/ModalDetalheOSAdmin';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { ModelosEquipamentoView } from './ModelosEquipamentoView';
import { mensagemErro, parseData } from '../utils/os';
import {
  Clock,
  Wrench,
  Building,
  Plus,
  Edit2,
  Search,
  AlertTriangle,
  Mail,
  Phone,
  MapPin,
  Car,
  Package,
  Calendar,
  Filter,
  UserCheck,
  UserX,
  Power,
  Receipt,
  X,
  Loader2,
} from 'lucide-react';

interface Props {
  onLogout?: () => void;
}

export type PeriodoFiltro = 'TODOS' | 'HOJE' | 'ULTIMOS_7' | 'ESTE_MES' | 'ULTIMOS_30' | 'CUSTOM';
export type StatusFilterAtividade = 'ATIVOS' | 'TODOS' | 'INATIVOS';

const moeda = (v: number) => v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export const AdminDashboardView: React.FC<Props> = ({ onLogout }) => {
  const [activeTab, setActiveTab] = useState<AdminTab>('dashboard');
  const [chamados, setChamados] = useState<OrdemServico[]>([]);
  const [canceladas, setCanceladas] = useState<OrdemServico[]>([]);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [tecnicos, setTecnicos] = useState<Tecnico[]>([]);

  const [loading, setLoading] = useState(true);
  const [loadErrors, setLoadErrors] = useState<string[]>([]);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [filtroStatusCliente, setFiltroStatusCliente] = useState<StatusFilterAtividade>('ATIVOS');
  const [filtroStatusTecnico, setFiltroStatusTecnico] = useState<StatusFilterAtividade>('ATIVOS');

  const [periodoSelecionado, setPeriodoSelecionado] = useState<PeriodoFiltro>('TODOS');
  const [dataInicioCustom, setDataInicioCustom] = useState('');
  const [dataFimCustom, setDataFimCustom] = useState('');

  const [showNovaOSModal, setShowNovaOSModal] = useState(false);
  const [osEdicao, setOsEdicao] = useState<OrdemServico | null>(null);

  const [showAtribuirModal, setShowAtribuirModal] = useState(false);
  const [osParaAtribuir, setOsParaAtribuir] = useState<OrdemServico | null>(null);

  const [osDetalheId, setOsDetalheId] = useState<number | null>(null);

  const [showClienteModal, setShowClienteModal] = useState(false);
  const [clienteEdicao, setClienteEdicao] = useState<Cliente | null>(null);

  const [showTecnicoModal, setShowTecnicoModal] = useState(false);
  const [tecnicoEdicao, setTecnicoEdicao] = useState<Tecnico | null>(null);

  const [clienteParaDesativar, setClienteParaDesativar] = useState<Cliente | null>(null);
  const [tecnicoParaDesativar, setTecnicoParaDesativar] = useState<Tecnico | null>(null);

  const [searchCliente, setSearchCliente] = useState('');
  const [searchTecnico, setSearchTecnico] = useState('');

  // Evita que uma resposta antiga sobrescreva uma carga mais recente.
  const cargaAtual = useRef(0);

  const loadData = useCallback(async () => {
    const id = ++cargaAtual.current;
    setLoading(true);
    const erros: string[] = [];
    let semConexao = false;
    const registrarErro = (rotulo: string, e: unknown) => {
      if (e instanceof ApiError && e.status === 0) semConexao = true;
      erros.push(`${rotulo}: ${mensagemErro(e)}`);
    };

    const [resCli, resTec] = await Promise.allSettled([ChamadoService.listarClientes(), ChamadoService.listarTecnicos()]);
    const listCli = resCli.status === 'fulfilled' ? resCli.value : [];
    const listTec = resTec.status === 'fulfilled' ? resTec.value : [];
    if (resCli.status === 'rejected') registrarErro('Clientes', resCli.reason);
    if (resTec.status === 'rejected') registrarErro('Técnicos', resTec.reason);

    const [resAtivas, resCanc] = await Promise.allSettled([
      ChamadoService.listarChamados(false, listCli, listTec),
      ChamadoService.listarChamados(true, listCli, listTec),
    ]);
    const listAtivas = resAtivas.status === 'fulfilled' ? resAtivas.value : [];
    const listCanc = resCanc.status === 'fulfilled' ? resCanc.value : [];
    if (resAtivas.status === 'rejected') registrarErro('Ordens de serviço', resAtivas.reason);
    if (resCanc.status === 'rejected') registrarErro('Ordens de serviço canceladas', resCanc.reason);

    if (id !== cargaAtual.current) return;

    // Em falha: erro claro + lista vazia (nunca dados fictícios ou em cache).
    setClientes(listCli);
    setTecnicos(listTec);
    setChamados(listAtivas);
    setCanceladas(listCanc);
    setLoadErrors(erros);
    setApiOnline(!semConexao);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // --- Filtro por período (data de abertura) ---
  const filtrarPorPeriodo = useCallback(
    (lista: OrdemServico[]): OrdemServico[] => {
      if (periodoSelecionado === 'TODOS') return lista;
      const agora = new Date();
      const inicioHoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate());
      const fimHoje = new Date(agora.getFullYear(), agora.getMonth(), agora.getDate(), 23, 59, 59, 999);

      return lista.filter((c) => {
        const dataOS = parseData(c.data_abertura);
        if (!dataOS) return false;
        if (periodoSelecionado === 'HOJE') return dataOS >= inicioHoje && dataOS <= fimHoje;
        if (periodoSelecionado === 'ULTIMOS_7' || periodoSelecionado === 'ULTIMOS_30') {
          const dias = periodoSelecionado === 'ULTIMOS_7' ? 7 : 30;
          const inicio = new Date(agora);
          inicio.setDate(agora.getDate() - dias);
          inicio.setHours(0, 0, 0, 0);
          return dataOS >= inicio && dataOS <= fimHoje;
        }
        if (periodoSelecionado === 'ESTE_MES') {
          return dataOS >= new Date(agora.getFullYear(), agora.getMonth(), 1) && dataOS <= fimHoje;
        }
        if (periodoSelecionado === 'CUSTOM') {
          if (!dataInicioCustom && !dataFimCustom) return true;
          const inicio = dataInicioCustom ? new Date(dataInicioCustom + 'T00:00:00') : new Date(0);
          const fim = dataFimCustom ? new Date(dataFimCustom + 'T23:59:59') : new Date(8640000000000000);
          return dataOS >= inicio && dataOS <= fim;
        }
        return true;
      });
    },
    [periodoSelecionado, dataInicioCustom, dataFimCustom]
  );

  const ativasPeriodo = useMemo(() => filtrarPorPeriodo(chamados), [chamados, filtrarPorPeriodo]);
  const canceladasPeriodo = useMemo(() => filtrarPorPeriodo(canceladas), [canceladas, filtrarPorPeriodo]);

  // Totais registrados nas visitas (dados reais da API). Não são o "custo da OS" calculado pelo servidor
  // (que usa valores globais e é congelado na finalização) e não incluem faturamento (fora do escopo).
  const totaisVisitas = useMemo(() => {
    let pedagioFrete = 0;
    let km = 0;
    let pecas = 0;
    ativasPeriodo.forEach((c) => {
      c.visitas.forEach((v) => {
        pedagioFrete += Number(v.valor_pedagio || 0) + Number(v.valor_frete_devolucao || 0);
        km += Number(v.km_total || 0);
        (v.servicos_realizados || []).forEach((s) =>
          (s.materiais_utilizados || []).forEach((m) => {
            pecas += Number(m.valor || 0) * Number(m.quantidade || 0);
          })
        );
      });
    });
    return { pedagioFrete, km, pecas };
  }, [ativasPeriodo]);

  const contarStatus = (status: (typeof STATUS_OS)[number]) => ativasPeriodo.filter((c) => c.status === status).length;
  const totalOS = ativasPeriodo.length + canceladasPeriodo.length;
  const finalizadasOS = contarStatus('Finalizado');
  const garantiaOS = ativasPeriodo.filter((c) => c.em_garantia).length;

  const osDetalhe = useMemo(
    () => (osDetalheId === null ? null : [...chamados, ...canceladas].find((c) => c.id_os === osDetalheId) || null),
    [osDetalheId, chamados, canceladas]
  );

  // --- Handlers: OS ---
  const handleSaveOS = async (data: DadosFormOS) => {
    if (data.id_os) {
      await ChamadoService.atualizarOrdemServico(data.id_os, {
        descricao_cliente: data.descricao_cliente,
        pedido: data.pedido,
        em_garantia: data.em_garantia,
      });
    } else {
      await ChamadoService.criarOrdemServico({
        id_cliente: data.id_cliente,
        id_tecnico_atribuido: data.id_tecnico_atribuido,
        data_agendamento: data.data_agendamento,
        descricao_cliente: data.descricao_cliente,
        em_garantia: data.em_garantia,
        pedido: data.pedido,
        // RN-41: equipamentos reais (modelo do catálogo + série digitada). O painel nunca cria visita.
        equipamentos: data.equipamentos,
      });
    }
    await loadData();
  };

  const handleConfirmAtribuir = async (id_os: number, id_tecnico: number) => {
    await ChamadoService.atribuirTecnico(id_os, id_tecnico);
    await loadData();
  };

  // --- Handlers: cliente ---
  const handleSaveCliente = async (data: Partial<Cliente>) => {
    await ChamadoService.salvarCliente(data);
    await loadData();
  };

  const handleToggleStatusCliente = async (cliente: Cliente) => {
    setActionError(null);
    try {
      await ChamadoService.reativarCliente(cliente.id_cliente);
      await loadData();
    } catch (e) {
      setActionError(`Não foi possível reativar o cliente: ${mensagemErro(e)}`);
    }
  };

  // --- Handlers: técnico ---
  const handleSaveTecnico = async (data: TecnicoPayload & { id_tecnico?: number }) => {
    await ChamadoService.salvarTecnico(data);
    await loadData();
  };

  const handleToggleStatusTecnico = async (tecnico: Tecnico) => {
    setActionError(null);
    try {
      await ChamadoService.reativarTecnico(tecnico.id_tecnico);
      await loadData();
    } catch (e) {
      setActionError(`Não foi possível reativar o técnico: ${mensagemErro(e)}`);
    }
  };

  const abrirNovaOS = () => {
    setOsEdicao(null);
    setShowNovaOSModal(true);
  };
  const abrirEdicaoOS = (os: OrdemServico) => {
    setOsEdicao(os);
    setShowNovaOSModal(true);
  };
  const abrirAtribuir = (os: OrdemServico) => {
    setOsParaAtribuir(os);
    setShowAtribuirModal(true);
  };

  const getTabTitle = () => {
    switch (activeTab) {
      case 'dashboard':
        return 'Painel de Controle Principal';
      case 'chamados':
        return 'Gestão de Ordens de Serviço';
      case 'clientes':
        return 'Cadastro de Clientes';
      case 'tecnicos':
        return 'Equipe de Atendimento Técnico';
      case 'modelos':
        return 'Catálogo de Modelos de Equipamento';
      default:
        return 'Painel Administrativo';
    }
  };

  const termoCliente = searchCliente.toLowerCase();
  const filteredClientes = clientes.filter((c) => {
    const matches =
      (c.razao_social || '').toLowerCase().includes(termoCliente) ||
      (c.cidade || '').toLowerCase().includes(termoCliente) ||
      String(c.codigo ?? '').includes(searchCliente.trim());
    if (!matches) return false;
    const ativo = c.is_active !== false;
    if (filtroStatusCliente === 'ATIVOS') return ativo;
    if (filtroStatusCliente === 'INATIVOS') return !ativo;
    return true;
  });

  const termoTecnico = searchTecnico.toLowerCase();
  const filteredTecnicos = tecnicos.filter((t) => {
    const matches = t.nome.toLowerCase().includes(termoTecnico) || (t.email || '').toLowerCase().includes(termoTecnico);
    if (!matches) return false;
    const ativo = t.is_active !== false;
    if (filtroStatusTecnico === 'ATIVOS') return ativo;
    if (filtroStatusTecnico === 'INATIVOS') return !ativo;
    return true;
  });

  const falhouCarregarOS = loadErrors.some((e) => e.startsWith('Ordens de serviço'));
  const tecnicosCampo = tecnicos.filter((t) => t.role !== 'admin');

  return (
    <div className="flex min-h-screen bg-background text-foreground font-sans">
      <Sidebar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        onOpenNovaOS={abrirNovaOS}
        totalOS={chamados.length}
        totalEmAtendimento={chamados.filter((c) => c.status === 'Em Atendimento').length}
        onLogout={onLogout}
      />

      <div className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        <AdminHeader
          activeTabTitle={getTabTitle()}
          totalChamados={chamados.length}
          totalFinalizadas={chamados.filter((c) => c.status === 'Finalizado').length}
          apiOnline={apiOnline}
          carregando={loading}
          onRefresh={loadData}
          onOpenNovaOS={abrirNovaOS}
          onLogout={onLogout}
        />

        <main className="p-6 space-y-6 max-w-7xl mx-auto w-full">
          {loadErrors.length > 0 && (
            <div
              role="alert"
              className="p-4 bg-destructive/10 border border-destructive/30 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-destructive"
            >
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                <div className="space-y-0.5">
                  <p className="font-bold">Não foi possível carregar todos os dados da API. As listas afetadas estão vazias.</p>
                  {loadErrors.map((e) => (
                    <p key={e}>{e}</p>
                  ))}
                </div>
              </div>
              <button
                onClick={loadData}
                className="px-3 py-1 bg-destructive text-white rounded-lg font-bold hover:bg-destructive/90 cursor-pointer shadow-xs self-end sm:self-auto"
              >
                Tentar novamente
              </button>
            </div>
          )}

          {actionError && (
            <div role="alert" className="p-3 bg-destructive/10 border border-destructive/30 rounded-2xl flex items-center justify-between gap-3 text-xs text-destructive">
              <span className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" /> {actionError}
              </span>
              <button onClick={() => setActionError(null)} aria-label="Dispensar aviso" className="p-1 cursor-pointer">
                <X className="w-4 h-4" />
              </button>
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center p-4 text-xs text-muted-foreground gap-2 bg-secondary/40 rounded-2xl border border-border">
              <Clock className="w-4 h-4 animate-spin text-accent" />
              <span>Consultando a API...</span>
            </div>
          )}

          {/* DASHBOARD */}
          {activeTab === 'dashboard' && (
            <div className="space-y-6">
              <div className="surface-card p-4 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="p-2.5 bg-primary/10 border border-primary/20 text-primary-strong rounded-xl">
                    <Calendar className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-foreground font-['Space_Grotesk']">Filtro de período</h3>
                    <p className="text-xs text-muted-foreground">
                      Considera a data de abertura e filtra indicadores, gráficos e lista desta tela
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {[
                    { id: 'TODOS', label: 'Todo o histórico' },
                    { id: 'HOJE', label: 'Hoje' },
                    { id: 'ULTIMOS_7', label: 'Últimos 7 dias' },
                    { id: 'ESTE_MES', label: 'Este mês' },
                    { id: 'ULTIMOS_30', label: 'Últimos 30 dias' },
                    { id: 'CUSTOM', label: 'Personalizado' },
                  ].map((item) => (
                    <button
                      key={item.id}
                      onClick={() => setPeriodoSelecionado(item.id as PeriodoFiltro)}
                      className={`px-3 py-1.5 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
                        periodoSelecionado === item.id
                          ? 'bg-accent text-white font-bold shadow-sm shadow-accent/20'
                          : 'bg-secondary text-muted-foreground hover:text-foreground border border-border hover:border-border/80'
                      }`}
                    >
                      {item.label}
                    </button>
                  ))}
                </div>
              </div>

              {periodoSelecionado === 'CUSTOM' && (
                <div className="surface-card p-4 flex flex-wrap items-center gap-4 text-xs">
                  <div className="flex items-center gap-2">
                    <label htmlFor="data-ini" className="text-muted-foreground font-semibold">Data inicial:</label>
                    <input
                      id="data-ini"
                      type="date"
                      value={dataInicioCustom}
                      onChange={(e) => setDataInicioCustom(e.target.value)}
                      className="bg-secondary border border-border rounded-xl px-3 py-1.5 text-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  <div className="flex items-center gap-2">
                    <label htmlFor="data-fim" className="text-muted-foreground font-semibold">Data final:</label>
                    <input
                      id="data-fim"
                      type="date"
                      value={dataFimCustom}
                      onChange={(e) => setDataFimCustom(e.target.value)}
                      className="bg-secondary border border-border rounded-xl px-3 py-1.5 text-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  {(dataInicioCustom || dataFimCustom) && (
                    <button
                      onClick={() => {
                        setDataInicioCustom('');
                        setDataFimCustom('');
                      }}
                      className="px-3 py-1.5 bg-secondary hover:bg-muted text-foreground rounded-xl text-xs font-semibold cursor-pointer border border-border"
                    >
                      Limpar datas
                    </button>
                  )}
                </div>
              )}

              {/* Totais registrados nas visitas */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                <div className="surface-card p-5 shadow-sm hover:border-accent/40 transition-all">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground">Quilometragem registrada</p>
                      <h3 className="text-2xl font-black text-foreground font-['Space_Grotesk'] mt-1">
                        {totaisVisitas.km.toLocaleString('pt-BR')} km
                      </h3>
                      <p className="text-[11px] text-muted-foreground mt-1">Soma do km total das visitas</p>
                    </div>
                    <div className="p-3 bg-accent/10 border border-accent/20 text-accent rounded-2xl">
                      <Car className="w-6 h-6" />
                    </div>
                  </div>
                </div>

                <div className="surface-card p-5 shadow-sm hover:border-success/40 transition-all">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground">Pedágio e frete registrados</p>
                      <h3 className="text-2xl font-black text-foreground font-['Space_Grotesk'] mt-1">{moeda(totaisVisitas.pedagioFrete)}</h3>
                      <p className="text-[11px] text-muted-foreground mt-1">Valores informados nas visitas</p>
                    </div>
                    <div className="p-3 bg-success/10 border border-success/20 text-success-strong rounded-2xl">
                      <Receipt className="w-6 h-6" />
                    </div>
                  </div>
                </div>

                <div className="surface-card p-5 shadow-sm hover:border-primary/40 transition-all">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-xs font-semibold text-muted-foreground">Peças e materiais registrados</p>
                      <h3 className="text-2xl font-black text-foreground font-['Space_Grotesk'] mt-1">{moeda(totaisVisitas.pecas)}</h3>
                      <p className="text-[11px] text-muted-foreground mt-1">Quantidade × valor informado</p>
                    </div>
                    <div className="p-3 bg-primary/10 border border-primary/20 text-primary-strong rounded-2xl">
                      <Package className="w-6 h-6" />
                    </div>
                  </div>
                </div>
              </div>
              <p className="text-[11px] text-muted-foreground -mt-3">
                Valores informados em campo, sem o cálculo de custo da OS (que usa os parâmetros globais e é congelado na
                finalização — veja o detalhe de cada OS).
              </p>

              {/* Indicadores por status */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <div className="surface-card p-4 shadow-sm">
                  <span className="text-[11px] font-semibold text-muted-foreground block">Total de OS (período)</span>
                  <div className="text-xl font-bold text-foreground font-['Space_Grotesk'] mt-0.5">{totalOS}</div>
                  <span className="text-[10px] text-accent font-medium">
                    {contarStatus('Pendente')} pendentes • {contarStatus('Em Atendimento')} em atendimento • {canceladasPeriodo.length} canceladas
                  </span>
                </div>

                <div className="surface-card p-4 shadow-sm">
                  <span className="text-[11px] font-semibold text-muted-foreground block">Finalizadas</span>
                  <div className="text-xl font-bold text-success-strong font-['Space_Grotesk'] mt-0.5">{finalizadasOS}</div>
                  <span className="text-[10px] text-success-strong font-medium">
                    {totalOS > 0 ? Math.round((finalizadasOS / totalOS) * 100) : 0}% do total
                  </span>
                </div>

                <div className="surface-card p-4 shadow-sm">
                  <span className="text-[11px] font-semibold text-muted-foreground block">Aguardando reagendamento</span>
                  <div className="text-xl font-bold text-purple-500 font-['Space_Grotesk'] mt-0.5">{contarStatus('Aguardando Reagendamento')}</div>
                  <span className="text-[10px] text-muted-foreground font-medium">{contarStatus('Pausado')} pausadas • {contarStatus('Agendado')} agendadas</span>
                </div>

                <div className="surface-card p-4 shadow-sm">
                  <span className="text-[11px] font-semibold text-muted-foreground block">Em garantia</span>
                  <div className="text-xl font-bold text-warning font-['Space_Grotesk'] mt-0.5">{garantiaOS}</div>
                  <span className="text-[10px] text-muted-foreground font-medium">entre as OS não canceladas</span>
                </div>
              </div>

              <DashboardCharts ativas={ativasPeriodo} canceladas={canceladasPeriodo} tecnicos={tecnicosCampo} />

              <TabelaOrdensServico
                ativas={ativasPeriodo}
                canceladas={canceladasPeriodo}
                carregando={loading}
                erroCarregamento={falhouCarregarOS}
                onSelectOS={(os) => setOsDetalheId(os.id_os)}
                onEditOS={abrirEdicaoOS}
                onAssignTecnico={abrirAtribuir}
                onOpenNovaOS={abrirNovaOS}
              />
            </div>
          )}

          {/* ORDENS DE SERVIÇO */}
          {activeTab === 'chamados' && (
            <TabelaOrdensServico
              ativas={chamados}
              canceladas={canceladas}
              carregando={loading}
              erroCarregamento={falhouCarregarOS}
              onSelectOS={(os) => setOsDetalheId(os.id_os)}
              onEditOS={abrirEdicaoOS}
              onAssignTecnico={abrirAtribuir}
              onOpenNovaOS={abrirNovaOS}
            />
          )}

          {/* CLIENTES */}
          {activeTab === 'clientes' && (
            <div className="surface-card p-6 shadow-sm space-y-6">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-foreground font-['Space_Grotesk'] flex items-center gap-2">
                    <Building className="w-5 h-5 text-accent" /> Cadastro e gestão de clientes
                  </h2>
                  <p className="text-xs text-muted-foreground">Gerencie os estabelecimentos atendidos pela FAST Gôndolas & Check-outs</p>
                </div>

                <div className="flex items-center gap-3">
                  <div className="relative flex-1 sm:w-64">
                    <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
                    <input
                      type="text"
                      aria-label="Buscar cliente"
                      placeholder="Buscar por nome, cidade ou código..."
                      value={searchCliente}
                      onChange={(e) => setSearchCliente(e.target.value)}
                      className="w-full bg-secondary border border-border rounded-xl py-2 pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={() => {
                      setClienteEdicao(null);
                      setShowClienteModal(true);
                    }}
                    className="py-2 px-4 bg-accent hover:bg-accent/90 text-white font-extrabold text-xs rounded-xl shadow-md flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Novo cliente</span>
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 p-1.5 bg-secondary/50 rounded-2xl border border-border w-fit text-xs">
                <span className="text-[11px] font-bold text-muted-foreground px-2 flex items-center gap-1">
                  <Filter className="w-3.5 h-3.5" /> Situação:
                </span>
                {(['ATIVOS', 'TODOS', 'INATIVOS'] as StatusFilterAtividade[]).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setFiltroStatusCliente(f)}
                    className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                      filtroStatusCliente === f
                        ? f === 'INATIVOS'
                          ? 'bg-amber-500 text-white shadow-xs'
                          : 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                    }`}
                  >
                    {f === 'ATIVOS' && <UserCheck className="w-3.5 h-3.5" />}
                    {f === 'INATIVOS' && <UserX className="w-3.5 h-3.5" />}
                    <span>{f === 'ATIVOS' ? 'Ativos' : f === 'TODOS' ? 'Todos' : 'Inativos'}</span>
                    <span className="px-1.5 rounded-full text-[10px] bg-background/20 font-extrabold">
                      {f === 'ATIVOS'
                        ? clientes.filter((c) => c.is_active !== false).length
                        : f === 'INATIVOS'
                        ? clientes.filter((c) => c.is_active === false).length
                        : clientes.length}
                    </span>
                  </button>
                ))}
              </div>

              {filteredClientes.length === 0 ? (
                <div className="p-12 text-center text-muted-foreground bg-secondary/30 rounded-2xl border border-dashed border-border">
                  {loading ? (
                    <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
                  ) : (
                    <Building className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  )}
                  <p className="font-bold text-foreground">
                    {loading
                      ? 'Carregando clientes...'
                      : loadErrors.some((e) => e.startsWith('Clientes'))
                      ? 'Não foi possível carregar os clientes.'
                      : filtroStatusCliente === 'INATIVOS'
                      ? 'Nenhum cliente inativo encontrado.'
                      : 'Nenhum cliente encontrado.'}
                  </p>
                  {!loading && !loadErrors.some((e) => e.startsWith('Clientes')) && (
                    <p className="text-xs mt-1">Use "Novo cliente" para cadastrar.</p>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {filteredClientes.map((cli) => {
                    const totalClienteOS = [...chamados, ...canceladas].filter((c) => c.id_cliente === cli.id_cliente).length;
                    const isAtivo = cli.is_active !== false;
                    return (
                      <div
                        key={cli.id_cliente}
                        className={`bg-card border rounded-2xl p-5 space-y-4 transition-all flex flex-col justify-between shadow-sm ${
                          isAtivo ? 'border-border hover:border-accent/40' : 'border-amber-500/30 bg-amber-500/5'
                        }`}
                      >
                        <div>
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="text-sm font-extrabold text-foreground">{cli.razao_social}</h3>
                                {isAtivo ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-success/10 text-success-strong border border-success/20">
                                    <UserCheck className="w-3 h-3" /> Ativo
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20">
                                    <UserX className="w-3 h-3" /> Inativo
                                  </span>
                                )}
                              </div>
                              {cli.codigo !== undefined && cli.codigo !== null && (
                                <p className="text-[11px] text-accent font-semibold">Código: {cli.codigo}</p>
                              )}
                            </div>
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-lg bg-secondary text-accent border border-border whitespace-nowrap">
                              {totalClienteOS} OS
                            </span>
                          </div>

                          <div className="mt-3 pt-3 border-t border-border space-y-2 text-xs text-foreground/90">
                            {cli.contato_principal_nome && (
                              <p className="flex items-center gap-2 text-muted-foreground">
                                <Phone className="w-3.5 h-3.5 text-success-strong shrink-0" />
                                <span>
                                  Contato: <strong className="text-foreground">{cli.contato_principal_nome}</strong>
                                  {cli.contato_principal_telefone ? ` (${cli.contato_principal_telefone})` : ''}
                                </span>
                              </p>
                            )}
                            <p className="flex items-center gap-2 text-muted-foreground">
                              <Phone className="w-3.5 h-3.5 text-primary-strong shrink-0" />
                              <span>
                                Telefone: <strong className="text-foreground">{cli.telefone || 'não informado'}</strong>
                              </span>
                            </p>
                            <p className="flex items-center gap-2 text-muted-foreground">
                              <MapPin className="w-3.5 h-3.5 shrink-0" />
                              <span>
                                {cli.endereco}, {cli.numero} - {cli.bairro}, {cli.cidade}/{cli.uf}
                              </span>
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                          <button
                            type="button"
                            onClick={() => {
                              setClienteEdicao(cli);
                              setShowClienteModal(true);
                            }}
                            className="px-3 py-1.5 bg-secondary hover:bg-muted text-accent border border-border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors"
                          >
                            <Edit2 className="w-3.5 h-3.5" /> Editar
                          </button>
                          <button
                            type="button"
                            onClick={() => (isAtivo ? setClienteParaDesativar(cli) : handleToggleStatusCliente(cli))}
                            className={`px-3 py-1.5 border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                              isAtivo
                                ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border-amber-500/30'
                                : 'bg-success/10 hover:bg-success/20 text-success-strong border-success/30'
                            }`}
                          >
                            <Power className="w-3.5 h-3.5" />
                            <span>{isAtivo ? 'Desativar' : 'Reativar'}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TÉCNICOS */}
          {activeTab === 'tecnicos' && (
            <div className="surface-card p-6 shadow-sm space-y-6">
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-bold text-foreground font-['Space_Grotesk'] flex items-center gap-2">
                    <Wrench className="w-5 h-5 text-accent" /> Equipe de técnicos de campo
                  </h2>
                  <p className="text-xs text-muted-foreground">Cadastre e supervisione os profissionais credenciados</p>
                </div>

                <div className="flex items-center gap-3">
                  <div className="relative flex-1 sm:w-64">
                    <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
                    <input
                      type="text"
                      aria-label="Buscar técnico"
                      placeholder="Buscar por nome ou e-mail..."
                      value={searchTecnico}
                      onChange={(e) => setSearchTecnico(e.target.value)}
                      className="w-full bg-secondary border border-border rounded-xl py-2 pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
                    />
                  </div>
                  <button
                    onClick={() => {
                      setTecnicoEdicao(null);
                      setShowTecnicoModal(true);
                    }}
                    className="py-2 px-4 bg-accent hover:bg-accent/90 text-white font-extrabold text-xs rounded-xl shadow-md flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Novo técnico</span>
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 p-1.5 bg-secondary/50 rounded-2xl border border-border w-fit text-xs">
                <span className="text-[11px] font-bold text-muted-foreground px-2 flex items-center gap-1">
                  <Filter className="w-3.5 h-3.5" /> Situação:
                </span>
                {(['ATIVOS', 'TODOS', 'INATIVOS'] as StatusFilterAtividade[]).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => setFiltroStatusTecnico(f)}
                    className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                      filtroStatusTecnico === f
                        ? f === 'INATIVOS'
                          ? 'bg-amber-500 text-white shadow-xs'
                          : 'bg-primary text-primary-foreground shadow-xs'
                        : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
                    }`}
                  >
                    {f === 'ATIVOS' && <UserCheck className="w-3.5 h-3.5" />}
                    {f === 'INATIVOS' && <UserX className="w-3.5 h-3.5" />}
                    <span>{f === 'ATIVOS' ? 'Ativos' : f === 'TODOS' ? 'Todos' : 'Inativos'}</span>
                    <span className="px-1.5 rounded-full text-[10px] bg-background/20 font-extrabold">
                      {f === 'ATIVOS'
                        ? tecnicos.filter((t) => t.is_active !== false).length
                        : f === 'INATIVOS'
                        ? tecnicos.filter((t) => t.is_active === false).length
                        : tecnicos.length}
                    </span>
                  </button>
                ))}
              </div>

              {filteredTecnicos.length === 0 ? (
                <div className="p-12 text-center text-muted-foreground bg-secondary/30 rounded-2xl border border-dashed border-border">
                  {loading ? (
                    <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
                  ) : (
                    <Wrench className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  )}
                  <p className="font-bold text-foreground">
                    {loading
                      ? 'Carregando técnicos...'
                      : loadErrors.some((e) => e.startsWith('Técnicos'))
                      ? 'Não foi possível carregar os técnicos.'
                      : filtroStatusTecnico === 'INATIVOS'
                      ? 'Nenhum técnico inativo encontrado.'
                      : 'Nenhum técnico encontrado.'}
                  </p>
                  {!loading && !loadErrors.some((e) => e.startsWith('Técnicos')) && (
                    <p className="text-xs mt-1">Use "Novo técnico" para cadastrar integrantes da equipe.</p>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {filteredTecnicos.map((tec) => {
                    const dele = chamados.filter((c) => c.id_tecnico_atribuido === tec.id_tecnico);
                    const ativasCount = dele.filter((c) => c.status !== 'Finalizado').length;
                    const finalizadasCount = dele.filter((c) => c.status === 'Finalizado').length;
                    const isAtivo = tec.is_active !== false;

                    return (
                      <div
                        key={tec.id_tecnico}
                        className={`bg-card border rounded-2xl p-5 space-y-4 transition-all flex flex-col justify-between shadow-sm ${
                          isAtivo ? 'border-border hover:border-accent/40' : 'border-amber-500/30 bg-amber-500/5'
                        }`}
                      >
                        <div className="space-y-3">
                          <div className="flex items-center gap-3">
                            <div className="w-12 h-12 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-primary-strong text-base">
                              {tec.nome.slice(0, 2).toUpperCase()}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center justify-between gap-1">
                                <h3 className="text-sm font-extrabold text-foreground truncate">{tec.nome}</h3>
                                {isAtivo ? (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-success/10 text-success-strong border border-success/20 shrink-0">
                                    <UserCheck className="w-3 h-3" /> Ativo
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20 shrink-0">
                                    <UserX className="w-3 h-3" /> Inativo
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-accent font-semibold">
                                {tec.role === 'admin' ? 'Administrador' : 'Técnico de campo'}
                              </p>
                            </div>
                          </div>

                          <div className="space-y-1.5 text-xs text-muted-foreground pt-2 border-t border-border">
                            <p className="flex items-center gap-2">
                              <Mail className="w-3.5 h-3.5 shrink-0" />
                              <span className="text-foreground/90 truncate">{tec.email}</span>
                            </p>
                            <p className="flex items-center gap-2">
                              <Phone className="w-3.5 h-3.5 text-success-strong shrink-0" />
                              <span className="text-foreground/90">{tec.telefone || 'Telefone não informado'}</span>
                            </p>
                            {tec.cpf && (
                              <p className="text-[11px] text-muted-foreground truncate">
                                CPF: <strong className="text-foreground">{tec.cpf}</strong>
                                {tec.cnpj ? (
                                  <>
                                    {' '}
                                    • CNPJ: <strong className="text-foreground">{tec.cnpj}</strong>
                                  </>
                                ) : null}
                              </p>
                            )}
                          </div>

                          <div className="grid grid-cols-2 gap-2 text-center text-xs pt-1">
                            <div className="bg-secondary p-2 rounded-xl border border-border">
                              <span className="text-[10px] text-muted-foreground block">OS em aberto</span>
                              <span className="font-extrabold text-accent">{ativasCount}</span>
                            </div>
                            <div className="bg-secondary p-2 rounded-xl border border-border">
                              <span className="text-[10px] text-muted-foreground block">Finalizadas</span>
                              <span className="font-extrabold text-success-strong">{finalizadasCount}</span>
                            </div>
                          </div>
                        </div>

                        <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                          <button
                            type="button"
                            onClick={() => {
                              setTecnicoEdicao(tec);
                              setShowTecnicoModal(true);
                            }}
                            className="px-3 py-1.5 bg-secondary hover:bg-muted text-accent border border-border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors"
                          >
                            <Edit2 className="w-3.5 h-3.5" /> Editar
                          </button>
                          <button
                            type="button"
                            onClick={() => (isAtivo ? setTecnicoParaDesativar(tec) : handleToggleStatusTecnico(tec))}
                            className={`px-3 py-1.5 border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors ${
                              isAtivo
                                ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border-amber-500/30'
                                : 'bg-success/10 hover:bg-success/20 text-success-strong border-success/30'
                            }`}
                          >
                            <Power className="w-3.5 h-3.5" />
                            <span>{isAtivo ? 'Desativar' : 'Reativar'}</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* MODELOS DE EQUIPAMENTO (carrega a própria lista ao abrir a aba) */}
          {activeTab === 'modelos' && <ModelosEquipamentoView />}
        </main>
      </div>

      <ModalNovaOS
        isOpen={showNovaOSModal}
        clientes={clientes}
        tecnicos={tecnicos}
        osEdicao={osEdicao}
        onClose={() => {
          setShowNovaOSModal(false);
          setOsEdicao(null);
        }}
        onSave={handleSaveOS}
      />

      <ModalAtribuirTecnico
        isOpen={showAtribuirModal}
        os={osParaAtribuir}
        tecnicos={tecnicos}
        onClose={() => {
          setShowAtribuirModal(false);
          setOsParaAtribuir(null);
        }}
        onConfirm={handleConfirmAtribuir}
      />

      <ModalCliente
        isOpen={showClienteModal}
        clienteEdicao={clienteEdicao}
        onClose={() => {
          setShowClienteModal(false);
          setClienteEdicao(null);
        }}
        onSave={handleSaveCliente}
      />

      <ModalTecnico
        isOpen={showTecnicoModal}
        tecnicoEdicao={tecnicoEdicao}
        onClose={() => {
          setShowTecnicoModal(false);
          setTecnicoEdicao(null);
        }}
        onSave={handleSaveTecnico}
      />

      <ModalDetalheOSAdmin
        isOpen={osDetalhe !== null}
        os={osDetalhe}
        onClose={() => setOsDetalheId(null)}
        onEdit={abrirEdicaoOS}
        onAssignTecnico={abrirAtribuir}
        onChanged={loadData}
      />

      {clienteParaDesativar && (
        <ConfirmDialog
          titulo="Desativar cliente"
          mensagem={
            <>
              Desativar o cliente <strong>{clienteParaDesativar.razao_social}</strong>? Ele deixa de receber novas OS; as OS e o
              histórico existentes são mantidos (desativação lógica).
            </>
          }
          textoConfirmar="Sim, desativar"
          onConfirm={async () => {
            await ChamadoService.desativarCliente(clienteParaDesativar.id_cliente);
            await loadData();
          }}
          onClose={() => setClienteParaDesativar(null)}
        />
      )}

      {tecnicoParaDesativar && (
        <ConfirmDialog
          titulo="Desativar técnico"
          mensagem={
            <>
              Desativar <strong>{tecnicoParaDesativar.nome}</strong>? O acesso ao aplicativo é bloqueado e ele deixa de poder
              receber novas OS (desativação lógica).
            </>
          }
          aviso={
            [...chamados].some((c) => c.id_tecnico_atribuido === tecnicoParaDesativar.id_tecnico && c.status !== 'Finalizado')
              ? 'Atenção: há OS não finalizadas atribuídas a este técnico. A reatribuição automática ainda depende de decisão do PO (RN-08a); reatribua manualmente, se necessário.'
              : undefined
          }
          textoConfirmar="Sim, desativar"
          onConfirm={async () => {
            await ChamadoService.desativarTecnico(tecnicoParaDesativar.id_tecnico);
            await loadData();
          }}
          onClose={() => setTecnicoParaDesativar(null)}
        />
      )}
    </div>
  );
};
