import React, { useEffect, useState } from 'react';
import {
  CustoTotalResponse,
  EstadoVisitaResponse,
  MotivoPausa,
  OrdemServico,
  RegistroPausa,
  ServicoEquipamento,
  Visita,
} from '../types';
import { StatusBadge } from './StatusBadge';
import { ModalPausa } from './ModalPausa';
import { ModalCancelarOS } from './ModalCancelarOS';
import { ModalReagendar } from './ModalReagendar';
import { SecaoEquipamentosOS } from './SecaoEquipamentosOS';
import { AssinaturaImagem } from './AssinaturaImagem';
import { FotoSegura } from './FotoSegura';
import { AjusteCusto, CorrecaoAdministrativaOS } from './CorrecaoAdministrativaOS';
import { ChamadoService } from '../services/chamadoService';
import {
  formatCpf,
  mascararCpf,
  formatData,
  formatDataHora,
  formatMoeda,
  mensagemErro,
  osTerminal,
  permissaoAtribuir,
  permissaoPausar,
  permissaoReagendar,
  podeCancelar,
  visitaAtual,
} from '../utils/os';
import {
  X,
  Building,
  Wrench,
  MapPin,
  ShieldCheck,
  FileText,
  PenTool,
  AlertTriangle,
  DollarSign,
  Image as ImageIcon,
  ExternalLink,
  Car,
  Layers,
  ZoomIn,
  PauseCircle,
  CalendarClock,
  XCircle,
  History,
  Loader2,
} from 'lucide-react';

interface Props {
  isOpen: boolean;
  os: OrdemServico | null;
  onClose: () => void;
  onEdit: (os: OrdemServico) => void;
  onAssignTecnico: (os: OrdemServico) => void;
  /** Recarrega as listas após uma ação (cancelar, pausar, reagendar). */
  onChanged: () => Promise<void>;
}

interface Foto {
  titulo: string;
  url: string;
}

const horaDe = (iso?: string | null, hhmm?: string | null): string => {
  if (iso) {
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  return hhmm || '--:--';
};

const kmDe = (km?: number | null): string => (km !== null && km !== undefined ? `${km} km` : 'km não registrado');

const listaDefeitos = (s: ServicoEquipamento): string[] =>
  [
    ...(s.defeitos_principais || []),
    ...(s.sub_defeitos_refrigeracao || []),
    ...(s.sub_defeitos_compressor || []),
    ...(s.sub_defeitos_vazamento || []),
    ...(s.sub_defeitos_outros || []),
    ...(s.sub_defeitos_iluminacao || []),
    ...(s.sub_defeitos_estrutura || []),
  ].filter(Boolean);

const Secao: React.FC<{ titulo: string; icone: React.ReactNode; children: React.ReactNode }> = ({ titulo, icone, children }) => (
  <div className="space-y-3">
    <span className="text-xs font-bold text-foreground flex items-center gap-1.5 uppercase tracking-wider">
      <span className="text-accent">{icone}</span> {titulo}
    </span>
    {children}
  </div>
);

const GaleriaFotos: React.FC<{ idOs: number; fotos: Foto[]; onOpen: (f: Foto) => void }> = ({ idOs, fotos, onOpen }) => {
  if (fotos.length === 0) {
    return <p className="text-[11px] text-muted-foreground">Nenhuma foto registrada.</p>;
  }
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {fotos.map((f, idx) => (
        <button
          type="button"
          key={`${f.url}-${idx}`}
          onClick={() => onOpen(f)}
          className="group bg-card border border-border rounded-xl p-2 space-y-1.5 text-left hover:border-accent/40 transition-all cursor-pointer"
        >
          <span className="text-[10px] font-bold text-foreground block truncate" title={f.titulo}>
            {f.titulo}
          </span>
          <span className="relative block aspect-video rounded-lg overflow-hidden bg-secondary border border-border">
            <FotoSegura idOs={idOs} url={f.url} alt={f.titulo} className="w-full h-full object-cover" />
            <span className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity">
              <ZoomIn className="w-5 h-5" />
            </span>
          </span>
        </button>
      ))}
    </div>
  );
};

function fotosDaVisita(v: Visita): Foto[] {
  const itens: Array<[string, string | null | undefined]> = [
    ['Odômetro: início', v.odometro_inicio_url],
    ['Odômetro: fim', v.odometro_fim_url],
    ['Ida: início', v.foto_inicio_ida_url],
    ['Ida: fim', v.foto_fim_ida_url],
    ['Volta: início', v.foto_inicio_volta_url],
    ['Volta: fim', v.foto_fim_volta_url],
  ];
  const fotos: Foto[] = itens.filter(([, url]) => Boolean(url)).map(([titulo, url]) => ({ titulo, url: url as string }));
  (v.comprovante_pedagio_urls || []).forEach((url, i) => fotos.push({ titulo: `Comprovante de pedágio ${i + 1}`, url }));
  (v.comprovante_frete_urls || []).forEach((url, i) => fotos.push({ titulo: `Comprovante de frete ${i + 1}`, url }));
  return fotos;
}

const PausaItem: React.FC<{ p: RegistroPausa }> = ({ p }) => (
  <div className="bg-amber-500/5 border border-amber-500/30 rounded-lg p-2.5 text-[11px] space-y-0.5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <span className="font-bold text-foreground flex items-center gap-1">
        <PauseCircle className="w-3.5 h-3.5 text-amber-600" /> {p.motivo}
      </span>
      <span className={p.is_ativa ? 'text-amber-600 font-bold' : 'text-muted-foreground'}>
        {p.is_ativa ? 'Pausa ativa' : 'Pausa encerrada'}
      </span>
    </div>
    {p.descricao && <p className="text-foreground/90">{p.descricao}</p>}
    <p className="text-muted-foreground">
      {p.por_papel ? `Registrada por ${p.por_papel === 'admin' ? 'administrador' : p.por_papel === 'tecnico' ? 'técnico' : p.por_papel}` : 'Autor não informado pela API'}
      {p.por_usuario_id ? ` (usuário #${p.por_usuario_id})` : ''}
      {p.criado_em ? ` • ${formatDataHora(p.criado_em)}` : ''}
    </p>
  </div>
);

export const ModalDetalheOSAdmin: React.FC<Props> = ({ isOpen, os, onClose, onEdit, onAssignTecnico, onChanged }) => {
  const [foto, setFoto] = useState<Foto | null>(null);
  const [showPausa, setShowPausa] = useState(false);
  const [showCancelar, setShowCancelar] = useState(false);
  const [showReagendar, setShowReagendar] = useState(false);
  // CPF do cliente mascarado por padrão (LGPD); botão "mostrar" por visita.
  const [cpfVisivel, setCpfVisivel] = useState<Record<number, boolean>>({});

  const [custos, setCustos] = useState<CustoTotalResponse | null>(null);
  const [custosErro, setCustosErro] = useState<string | null>(null);
  const [custosCarregando, setCustosCarregando] = useState(false);
  // Total anterior → novo após corrigir materiais em OS Finalizada (RN-49).
  const [ajusteCusto, setAjusteCusto] = useState<AjusteCusto | null>(null);

  const [estado, setEstado] = useState<EstadoVisitaResponse | null>(null);
  const [estadoErro, setEstadoErro] = useState<string | null>(null);

  const idOs = os?.id_os;

  useEffect(() => {
    setCpfVisivel({});
    setAjusteCusto(null);
  }, [idOs]);
  const statusOs = os?.status;
  const cancelada = os?.is_cancelled;
  const idVisitaAtual = os ? visitaAtual(os)?.id_visita : undefined;

  // Custos: para OS Finalizada a API devolve o snapshot congelado (RN-33); caso contrário, cálculo atual.
  useEffect(() => {
    setCustos(null);
    setCustosErro(null);
    if (!isOpen || idOs === undefined || cancelada) return;
    let ativo = true;
    setCustosCarregando(true);
    ChamadoService.calcularCustos(idOs)
      .then((c) => ativo && setCustos(c))
      .catch((e) => ativo && setCustosErro(mensagemErro(e, 'Não foi possível carregar os custos.')))
      .finally(() => ativo && setCustosCarregando(false));
    return () => {
      ativo = false;
    };
  }, [isOpen, idOs, statusOs, cancelada]);

  // Estado da visita (GET .../estado) para habilitar "Pausar" conforme a API.
  useEffect(() => {
    setEstado(null);
    setEstadoErro(null);
    if (!isOpen || idOs === undefined || idVisitaAtual === undefined || cancelada) return;
    if (statusOs !== 'Em Atendimento' && statusOs !== 'Pausado') return;
    let ativo = true;
    ChamadoService.getEstadoVisita(idOs, idVisitaAtual)
      .then((e) => ativo && setEstado(e))
      .catch((e) => ativo && setEstadoErro(mensagemErro(e, 'Estado da visita indisponível.')));
    return () => {
      ativo = false;
    };
  }, [isOpen, idOs, idVisitaAtual, statusOs, cancelada]);

  if (!isOpen || !os) return null;

  const c = os.cliente;
  const t = os.tecnico;
  const visitaPausa = visitaAtual(os);

  const permPausar = permissaoPausar(os);
  const pausarBloqueadoPelaApi = estado !== null && estado.pode_pausar_os === false;
  const pausarHabilitado = permPausar.permitido && !pausarBloqueadoPelaApi;
  const permReagendar = permissaoReagendar(os);
  const permAtribuir = permissaoAtribuir(os);

  const handleConfirmarPausa = async (motivo: MotivoPausa, descricao?: string) => {
    if (!visitaPausa) throw new Error('Nenhuma visita encontrada para pausar.');
    await ChamadoService.pausarVisita(os.id_os, visitaPausa.id_visita, motivo, descricao);
    await onChanged();
  };

  // Após corrigir materiais: relê GET /custos (o servidor substituiu o snapshot) e mostra total anterior → novo.
  const handleMateriaisCorrigidos = async () => {
    const anterior = ajusteCusto ? ajusteCusto.novo : custos ? custos.total_geral : null;
    const novo = await ChamadoService.calcularCustos(os.id_os);
    setCustos(novo);
    setCustosErro(null);
    setAjusteCusto({ anterior, novo: novo.total_geral });
  };

  const handleConfirmarCancelamento = async (motivo: string) => {
    await ChamadoService.cancelarChamado(os.id_os, motivo);
    await onChanged();
  };

  const handleConfirmarReagendamento = async (data: string) => {
    await ChamadoService.reagendarChamado(os.id_os, data);
    await onChanged();
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto font-sans">
      <div className="w-full max-w-5xl bg-card border border-border rounded-3xl p-6 shadow-2xl relative my-6 max-h-[92vh] flex flex-col text-foreground">
        {/* Cabeçalho */}
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-border pb-4 mb-5 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-accent/10 border border-accent/20 text-accent rounded-2xl">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h2 className="text-xl font-extrabold text-foreground font-['Space_Grotesk'] tracking-tight">
                  Ordem de Serviço #{os.codigo_os}
                </h2>
                <StatusBadge status={os.status} cancelada={os.is_cancelled} size="md" />
                {os.em_garantia && (
                  <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-success/10 text-success-strong border border-success/30 flex items-center gap-1">
                    <ShieldCheck className="w-3.5 h-3.5" /> Garantia
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-1 flex items-center gap-3 flex-wrap">
                <span>
                  Abertura: <strong className="text-foreground">{formatData(os.data_abertura)}</strong>
                </span>
                <span>•</span>
                <span>
                  Agendamento:{' '}
                  <strong className="text-accent">{os.data_agendamento ? formatData(os.data_agendamento) : 'Não agendado'}</strong>
                </span>
                {os.data_conclusao && (
                  <>
                    <span>•</span>
                    <span>
                      Conclusão: <strong className="text-foreground">{formatData(os.data_conclusao)}</strong>
                    </span>
                  </>
                )}
                {os.pedido && (
                  <>
                    <span>•</span>
                    <span>
                      Pedido: <strong className="text-foreground">{os.pedido}</strong>
                    </span>
                  </>
                )}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {!osTerminal(os) && (
              <button
                onClick={() => {
                  onClose();
                  onEdit(os);
                }}
                className="px-3.5 py-2 bg-accent/10 hover:bg-accent/20 text-accent border border-accent/30 rounded-xl text-xs font-bold cursor-pointer"
              >
                Editar OS
              </button>
            )}

            {permAtribuir.permitido && (
              <button
                onClick={() => onAssignTecnico(os)}
                className="px-3.5 py-2 bg-secondary hover:bg-muted text-foreground border border-border rounded-xl text-xs font-bold cursor-pointer"
              >
                {os.id_tecnico_atribuido ? 'Reatribuir técnico' : 'Atribuir técnico'}
              </button>
            )}

            {!osTerminal(os) && (
              <button
                onClick={() => setShowReagendar(true)}
                disabled={!permReagendar.permitido}
                title={permReagendar.permitido ? 'Reagendar a visita' : permReagendar.motivo}
                className="px-3.5 py-2 bg-primary/10 hover:bg-primary/20 text-primary-strong border border-primary/30 rounded-xl text-xs font-bold cursor-pointer flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <CalendarClock className="w-4 h-4" /> Reagendar
              </button>
            )}

            {!osTerminal(os) && os.status === 'Em Atendimento' && (
              <button
                onClick={() => setShowPausa(true)}
                disabled={!pausarHabilitado}
                title={
                  pausarHabilitado
                    ? 'Pausar a OS em atendimento'
                    : permPausar.motivo || 'A API informa que esta visita não pode ser pausada agora.'
                }
                className="px-3.5 py-2 bg-amber-500/10 hover:bg-amber-500/20 text-amber-600 border border-amber-500/30 rounded-xl text-xs font-bold cursor-pointer flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <PauseCircle className="w-4 h-4" /> Pausar
              </button>
            )}

            {podeCancelar(os) && (
              <button
                onClick={() => setShowCancelar(true)}
                className="px-3 py-2 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/30 rounded-xl text-xs font-bold cursor-pointer flex items-center gap-1.5"
              >
                <XCircle className="w-4 h-4" /> Cancelar OS
              </button>
            )}

            <button
              onClick={onClose}
              aria-label="Fechar"
              className="p-2 text-muted-foreground hover:text-foreground rounded-xl hover:bg-secondary transition-colors cursor-pointer"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Corpo */}
        <div className="space-y-6 text-xs overflow-y-auto pr-1 flex-1">
          {os.is_cancelled && (
            <div className="p-4 bg-destructive/10 border border-destructive/30 rounded-2xl space-y-1">
              <p className="font-bold text-destructive flex items-center gap-2">
                <XCircle className="w-4 h-4" /> OS cancelada
              </p>
              <p className="text-foreground">
                <strong>Motivo:</strong> {os.motivo_cancelamento || 'não informado pela API'}
              </p>
              <p className="text-muted-foreground">
                {os.cancelado_em ? `Em ${formatDataHora(os.cancelado_em)}` : 'Data do cancelamento não informada'}
                {os.cancelado_por ? ` • por administrador #${os.cancelado_por}` : ''}
              </p>
            </div>
          )}

          {os.status === 'Pausado' && !os.is_cancelled && (
            <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-2xl space-y-1 text-foreground">
              <p className="font-bold text-amber-700 flex items-center gap-2">
                <PauseCircle className="w-4 h-4" /> OS pausada
              </p>
              {estado?.motivo_pausa && (
                <p>
                  <strong>Motivo:</strong> {estado.motivo_pausa}
                </p>
              )}
              <p className="text-muted-foreground">
                Reagendamento indisponível até o técnico finalizar o deslocamento de volta; depois a OS passa para "Aguardando
                Reagendamento".
              </p>
            </div>
          )}

          {estadoErro && <p className="text-[11px] text-muted-foreground">Estado da visita: {estadoErro}</p>}

          {/* Envolvidos e custos */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-secondary/40 p-4 rounded-2xl border border-border space-y-2.5">
              <div className="flex items-center justify-between text-[11px] font-bold uppercase tracking-wider">
                <span className="flex items-center gap-1.5 text-accent">
                  <Building className="w-4 h-4" /> Cliente solicitante
                </span>
                {c.codigo !== undefined && <span className="text-muted-foreground">Código {c.codigo}</span>}
              </div>
              <h3 className="text-sm font-extrabold text-foreground">{c.razao_social}</h3>
              <div className="pt-2 border-t border-border space-y-1.5">
                <p className="text-foreground font-semibold">
                  Contato:{' '}
                  <span className="text-accent font-bold">{c.contato_principal_nome || 'não informado'}</span>
                  {c.contato_principal_telefone || c.telefone ? ` (${c.contato_principal_telefone || c.telefone})` : ''}
                </p>
                {c.endereco && (
                  <p className="text-muted-foreground text-[11px] flex items-center justify-between gap-2">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 shrink-0" />
                      {c.endereco}, {c.numero} - {c.bairro}, {c.cidade}/{c.uf}
                    </span>
                    <a
                      href={`https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${c.endereco}, ${c.numero}, ${c.cidade} ${c.uf}`)}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-accent hover:underline flex items-center gap-0.5 text-[10px] shrink-0 font-medium"
                    >
                      <span>Ver no Maps</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  </p>
                )}
              </div>
            </div>

            <div className="bg-secondary/40 p-4 rounded-2xl border border-border space-y-3">
              <div>
                <span className="flex items-center gap-1.5 text-accent text-[11px] font-bold uppercase tracking-wider mb-2">
                  <Wrench className="w-4 h-4" /> Técnico de campo atribuído
                </span>
                {t ? (
                  <div className="flex items-center gap-3 bg-card p-3 rounded-xl border border-border">
                    <div className="w-12 h-12 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center font-bold text-primary-strong text-sm">
                      {t.nome.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-foreground">{t.nome}</h3>
                      <p className="text-[11px] text-muted-foreground">{t.email}</p>
                      {t.telefone && <p className="text-[11px] text-success-strong font-semibold mt-0.5">{t.telefone}</p>}
                    </div>
                  </div>
                ) : os.id_tecnico_atribuido ? (
                  <div className="p-4 bg-card rounded-xl border border-border text-muted-foreground">
                    Técnico #{os.id_tecnico_atribuido} (dados não carregados).
                  </div>
                ) : (
                  <div className="p-4 bg-card rounded-xl border border-border text-center text-muted-foreground">
                    Nenhum técnico atribuído a esta OS.
                  </div>
                )}
              </div>

              <div className="bg-card p-3.5 rounded-xl border border-border space-y-2">
                <div className="flex items-center justify-between text-xs font-bold text-foreground">
                  <span className="flex items-center gap-1 text-accent">
                    <DollarSign className="w-4 h-4" /> Custo interno da OS
                  </span>
                  {custos && <span className="text-sm font-extrabold">{formatMoeda(custos.total_geral)}</span>}
                </div>
                {os.is_cancelled ? (
                  <p className="text-[11px] text-muted-foreground">Custo não exibido para OS cancelada.</p>
                ) : custosCarregando ? (
                  <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> Carregando custos...
                  </p>
                ) : custosErro ? (
                  <p className="text-[11px] text-destructive">{custosErro}</p>
                ) : custos ? (
                  <>
                    <p className="text-[10px] text-muted-foreground">
                      {os.status === 'Finalizado'
                        ? 'Valores congelados na finalização da OS.'
                        : 'Cálculo parcial com os valores globais atuais; será congelado na finalização.'}{' '}
                      Registro interno, não cobrado do cliente.
                    </p>
                    <div className="grid grid-cols-3 gap-2 text-[10px] pt-1 border-t border-border">
                      <div>
                        <span className="text-muted-foreground block">Materiais</span>
                        <strong>{formatMoeda(custos.custo_total_materiais)}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">Quilometragem</span>
                        <strong>{formatMoeda(custos.custo_total_km)}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">Pedágio</span>
                        <strong>{formatMoeda(custos.custo_total_pedagio)}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">Frete</span>
                        <strong>{formatMoeda(custos.custo_total_frete)}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">Tempo de serviço</span>
                        <strong>{formatMoeda(custos.custo_total_servico)}</strong>
                      </div>
                      <div>
                        <span className="text-muted-foreground block">Deslocamento</span>
                        <strong>{formatMoeda(custos.custo_total_deslocamento)}</strong>
                      </div>
                    </div>
                  </>
                ) : null}
              </div>
            </div>
          </div>

          {/* Solicitação */}
          <div className="bg-secondary/40 p-4 rounded-2xl border border-border space-y-1.5">
            <span className="text-[11px] font-bold text-accent uppercase tracking-wider flex items-center gap-1.5">
              <FileText className="w-3.5 h-3.5" /> Descrição da solicitação
            </span>
            <p className="text-foreground leading-relaxed font-medium bg-card p-3 rounded-xl border border-border whitespace-pre-wrap">
              {os.descricao_cliente || 'Sem descrição.'}
            </p>
          </div>

          {/* Equipamentos da OS (v0.5): edição só até o início do atendimento (RN-45) */}
          <SecaoEquipamentosOS key={os.id_os} os={os} onChanged={onChanged} />

          {/* Visitas */}
          <Secao titulo={`Visitas (${os.visitas.length})`} icone={<Car className="w-4 h-4" />}>
            {os.visitas.length === 0 ? (
              <p className="text-muted-foreground bg-secondary/40 p-4 rounded-2xl border border-border">
                Nenhuma visita registrada ainda para esta OS.
              </p>
            ) : (
              <div className="space-y-4">
                {[...os.visitas]
                  .sort((a, b) => a.id_visita - b.id_visita)
                  .map((v, idx) => {
                    const servicos = v.servicos_realizados || [];
                    return (
                      <div key={v.id_visita} className="bg-secondary/40 p-5 rounded-2xl border border-border space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h4 className="font-bold text-foreground text-xs uppercase tracking-wider">
                            Visita {idx + 1} • {formatData(v.data_visita)}
                          </h4>
                          <span
                            className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${
                              v.servico_finalizado
                                ? 'bg-success/10 text-success-strong border-success/30'
                                : 'bg-secondary text-muted-foreground border-border'
                            }`}
                          >
                            {v.servico_finalizado ? 'Visita encerrada' : 'Visita em andamento/pendente'}
                          </span>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                          <div className="bg-card p-3 rounded-xl border border-border">
                            <span className="text-[10px] text-muted-foreground block font-semibold">Ida: início</span>
                            <span className="text-sm font-extrabold">{horaDe(v.ida_inicio_em, v.hora_inicio_ida)}</span>
                            <span className="text-[11px] text-accent font-bold block mt-1">{kmDe(v.km_inicio_ida)}</span>
                          </div>
                          <div className="bg-card p-3 rounded-xl border border-border">
                            <span className="text-[10px] text-muted-foreground block font-semibold">Ida: fim (chegada)</span>
                            <span className="text-sm font-extrabold">{horaDe(v.ida_fim_em, v.hora_fim_ida || v.hora_chegada_cliente)}</span>
                            <span className="text-[11px] text-success-strong font-bold block mt-1">{kmDe(v.km_fim_ida)}</span>
                          </div>
                          <div className="bg-card p-3 rounded-xl border border-border">
                            <span className="text-[10px] text-muted-foreground block font-semibold">Volta: início</span>
                            <span className="text-sm font-extrabold">{horaDe(v.volta_inicio_em, v.hora_inicio_volta)}</span>
                            <span className="text-[11px] font-bold block mt-1">{kmDe(v.km_inicio_volta)}</span>
                          </div>
                          <div className="bg-card p-3 rounded-xl border border-border">
                            <span className="text-[10px] text-muted-foreground block font-semibold">Volta: fim • total</span>
                            <span className="text-sm font-extrabold">{horaDe(v.volta_fim_em, v.hora_fim_volta)}</span>
                            <span className="text-[11px] text-accent font-extrabold block mt-1">
                              {v.km_total ? `${v.km_total} km total` : kmDe(v.km_fim_volta)}
                            </span>
                          </div>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[11px]">
                          <p className="text-muted-foreground">
                            Atendimento:{' '}
                            <strong className="text-foreground">
                              {horaDe(v.atendimento_inicio_em, v.hora_inicio_atendimento)} –{' '}
                              {horaDe(v.atendimento_fim_em, v.hora_fim_atendimento)}
                            </strong>
                          </p>
                          <p className="text-muted-foreground">
                            Pedágio: <strong className="text-foreground">{formatMoeda(v.valor_pedagio)}</strong>
                          </p>
                          <p className="text-muted-foreground">
                            Frete de devolução: <strong className="text-foreground">{formatMoeda(v.valor_frete_devolucao)}</strong>
                          </p>
                          {v.pendencia && (
                            <p className="text-muted-foreground">
                              Pendência: <strong className="text-foreground">{v.pendencia}</strong>
                            </p>
                          )}
                        </div>

                        {v.descricao_servico_executado && (
                          <p className="text-foreground bg-card p-3 rounded-xl border border-border whitespace-pre-wrap">
                            {v.descricao_servico_executado}
                          </p>
                        )}

                        {(v.pausas || []).length > 0 && (
                          <Secao titulo="Pausas" icone={<PauseCircle className="w-4 h-4" />}>
                            <div className="space-y-2">
                              {(v.pausas || []).map((p) => (
                                <PausaItem key={p.id_pausa} p={p} />
                              ))}
                            </div>
                          </Secao>
                        )}

                        <Secao titulo="Fotos e comprovantes" icone={<ImageIcon className="w-4 h-4" />}>
                          <GaleriaFotos idOs={os.id_os} fotos={fotosDaVisita(v)} onOpen={setFoto} />
                        </Secao>

                        <Secao titulo={`Serviços por equipamento (${servicos.length})`} icone={<Wrench className="w-4 h-4" />}>
                          {servicos.length === 0 ? (
                            <p className="text-[11px] text-muted-foreground">Nenhum serviço registrado nesta visita.</p>
                          ) : (
                            <div className="space-y-3">
                              {servicos.map((s, i) => {
                                const defeitos = listaDefeitos(s);
                                const materiais = s.materiais_utilizados || [];
                                const fotos: Foto[] = [
                                  ...(s.fotos_defeito || []).map((url, k) => ({ titulo: `Defeito ${k + 1}`, url })),
                                  ...(s.fotos_conserto || []).map((url, k) => ({ titulo: `Conserto ${k + 1}`, url })),
                                ];
                                return (
                                  <div key={s.id_servico ?? i} className="bg-card p-4 rounded-xl border border-border space-y-3">
                                    <div className="flex flex-wrap items-start justify-between gap-2">
                                      <div>
                                        <h5 className="font-extrabold text-foreground text-xs">
                                          {s.modelo || s.nome_equipamento || 'Equipamento sem modelo informado'}
                                        </h5>
                                        <p className="text-[11px] text-muted-foreground">
                                          Nº de série:{' '}
                                          <span className="text-accent">
                                            {s.numero_serie || s.numero_serie_atendido || 'não informado'}
                                          </span>
                                        </p>
                                      </div>
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        {s.is_legado && (
                                          <span
                                            className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-secondary text-muted-foreground border border-border"
                                            title="Registro anterior à regra de equipamento da OS (sem vínculo com o catálogo)."
                                          >
                                            Registro legado
                                          </span>
                                        )}
                                        <span
                                          className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                                            s.conserto_salvo_em
                                              ? 'bg-success/10 text-success-strong border-success/30'
                                              : 'bg-amber-500/10 text-amber-600 border-amber-500/30'
                                          }`}
                                        >
                                          {s.conserto_salvo_em
                                            ? `Conserto salvo em ${formatDataHora(s.conserto_salvo_em)}`
                                            : 'Conserto não salvo'}
                                        </span>
                                      </div>
                                    </div>

                                    {defeitos.length > 0 && (
                                      <div className="pt-2 border-t border-border">
                                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider block mb-1">
                                          Defeitos apontados
                                        </span>
                                        <div className="flex flex-wrap gap-1.5">
                                          {defeitos.map((d, k) => (
                                            <span key={`${d}-${k}`} className="px-2 py-0.5 rounded-md bg-secondary border border-border text-[11px]">
                                              {d}
                                            </span>
                                          ))}
                                        </div>
                                        {s.defeito_outros_descricao && (
                                          <p className="text-[11px] text-foreground mt-1">Outros: {s.defeito_outros_descricao}</p>
                                        )}
                                        {s.vazamento_ponto_descricao && (
                                          <p className="text-[11px] text-foreground mt-1">Pontos de vazamento: {s.vazamento_ponto_descricao}</p>
                                        )}
                                      </div>
                                    )}

                                    {materiais.length > 0 && (
                                      <div className="pt-2 border-t border-border space-y-1.5">
                                        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider block">
                                          Peças e materiais
                                        </span>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                          {materiais.map((m, k) => (
                                            <div
                                              key={m.id_material ?? k}
                                              className="bg-secondary/50 p-2 rounded-lg border border-border text-[11px] flex justify-between items-center"
                                            >
                                              <span className="text-foreground font-medium">
                                                {m.quantidade}x {m.nome}
                                              </span>
                                              <span className="text-accent font-bold text-[10px]">
                                                {formatMoeda(Number(m.quantidade) * Number(m.valor))}
                                              </span>
                                            </div>
                                          ))}
                                        </div>
                                      </div>
                                    )}

                                    {fotos.length > 0 && (
                                      <div className="pt-2 border-t border-border">
                                        <GaleriaFotos idOs={os.id_os} fotos={fotos} onOpen={setFoto} />
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </Secao>

                        <Secao titulo="Assinatura do cliente" icone={<PenTool className="w-4 h-4" />}>
                          {v.assinatura_url ? (
                            <div className="bg-card p-4 rounded-2xl border border-border flex flex-wrap items-center justify-between gap-4">
                              <div>
                                <p className="text-foreground font-extrabold text-sm">{v.nome_cliente_assinatura || 'Nome não informado'}</p>
                                <p className="text-muted-foreground text-[11px] flex items-center gap-2">
                                  CPF:{' '}
                                  <span className="text-foreground">
                                    {cpfVisivel[v.id_visita] ? formatCpf(v.documento_cliente) : mascararCpf(v.documento_cliente)}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() => setCpfVisivel((prev) => ({ ...prev, [v.id_visita]: !prev[v.id_visita] }))}
                                    className="text-accent hover:underline font-semibold cursor-pointer"
                                  >
                                    {cpfVisivel[v.id_visita] ? 'ocultar' : 'mostrar'}
                                  </button>
                                </p>
                              </div>
                              <AssinaturaImagem
                                idOs={os.id_os}
                                idVisita={v.id_visita}
                                onAbrir={(url) => setFoto({ titulo: 'Assinatura do cliente', url })}
                              />
                            </div>
                          ) : (
                            <p className="text-[11px] text-muted-foreground">Assinatura não coletada nesta visita.</p>
                          )}
                        </Secao>
                      </div>
                    );
                  })}
              </div>
            )}
          </Secao>

          {/* Correção administrativa: somente OS Finalizada e não cancelada (RN-49) */}
          {os.status === 'Finalizado' && !os.is_cancelled && (
            <Secao titulo="Correção administrativa" icone={<Wrench className="w-4 h-4" />}>
              <CorrecaoAdministrativaOS
                os={os}
                ajusteCusto={ajusteCusto}
                onMateriaisCorrigidos={handleMateriaisCorrigidos}
                onChanged={onChanged}
                onAbrirFoto={(titulo, url) => setFoto({ titulo, url })}
              />
            </Secao>
          )}

          {/* Histórico */}
          <Secao titulo="Histórico de ações" icone={<History className="w-4 h-4" />}>
            <p className="text-[11px] text-muted-foreground bg-secondary/40 p-3 rounded-xl border border-dashed border-border flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                A trilha de auditoria (quem fez o quê e quando) ainda não é exposta pela API. Pendência: endpoint de histórico
                baseado em <code>log_acao</code> (PR-20 / RF-17).
              </span>
            </p>
          </Secao>
        </div>

        <div className="pt-4 border-t border-border flex items-center justify-between mt-4 shrink-0">
          <span className="text-[11px] text-muted-foreground flex items-center gap-1">
            <Layers className="w-3.5 h-3.5" /> FAST Gôndolas & Check-outs • OS #{os.codigo_os}
          </span>
          <button
            onClick={onClose}
            className="px-5 py-2.5 bg-secondary hover:bg-muted text-foreground rounded-xl font-bold cursor-pointer text-xs"
          >
            Fechar
          </button>
        </div>
      </div>

      {foto && (
        <div className="fixed inset-0 z-[60] bg-black/90 flex flex-col items-center justify-center p-4" onClick={() => setFoto(null)}>
          <div className="relative max-w-3xl w-full text-center space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between text-white pb-2 border-b border-white/20">
              <span className="font-bold text-sm">{foto.titulo}</span>
              <button onClick={() => setFoto(null)} aria-label="Fechar imagem" className="p-1 text-white/70 hover:text-white">
                <X className="w-6 h-6" />
              </button>
            </div>
            {foto.url.startsWith('blob:') ? (
              <img
                src={foto.url}
                alt={foto.titulo}
                className="max-h-[75vh] w-auto mx-auto rounded-2xl border border-white/20 shadow-2xl object-contain"
              />
            ) : (
              <div className="min-h-[8rem] flex items-center justify-center text-white">
                <FotoSegura
                  idOs={os.id_os}
                  url={foto.url}
                  alt={foto.titulo}
                  className="max-h-[75vh] w-auto mx-auto rounded-2xl border border-white/20 shadow-2xl object-contain"
                />
              </div>
            )}
          </div>
        </div>
      )}

      <ModalPausa
        isOpen={showPausa}
        codigoOS={os.codigo_os}
        onClose={() => setShowPausa(false)}
        onConfirm={handleConfirmarPausa}
      />
      <ModalCancelarOS
        isOpen={showCancelar}
        codigoOS={os.codigo_os}
        onClose={() => setShowCancelar(false)}
        onConfirm={handleConfirmarCancelamento}
      />
      <ModalReagendar
        isOpen={showReagendar}
        codigoOS={os.codigo_os}
        status={os.status}
        onClose={() => setShowReagendar(false)}
        onConfirm={handleConfirmarReagendamento}
      />
    </div>
  );
};
