import React, { useState, useEffect } from 'react';
import { Cliente, Tecnico, OrdemServico } from '../types';
import {
  Sparkles,
  Building,
  Wrench,
  Calendar,
  ShieldCheck,
  AlertCircle,
  Loader2,
  Package,
  Plus,
  Trash2,
} from 'lucide-react';
import { ModalShell } from './ModalShell';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';
import { useModelosAtivos } from '../hooks/useModelosAtivos';
import { OsEquipamentoPayload } from '../services/apiClient';
import { formatData } from '../utils/os';

export interface DadosFormOS {
  id_os?: number;
  id_cliente: number;
  id_tecnico_atribuido: number | null;
  data_agendamento: string | null;
  descricao_cliente: string;
  em_garantia: boolean;
  pedido: string;
  /** Somente na criação (RN-41). Na edição os equipamentos são mantidos no detalhe da OS. */
  equipamentos: OsEquipamentoPayload[];
}

interface LinhaEquipamento {
  chave: number;
  idModelo: number;
  serie: string;
}

const SERIE_MAX = 100;
let proximaChave = 1;
const novaLinha = (): LinhaEquipamento => ({ chave: proximaChave++, idModelo: 0, serie: '' });
const chaveSerie = (s: string) => s.trim().toUpperCase();

interface Props {
  isOpen: boolean;
  clientes: Cliente[];
  tecnicos: Tecnico[];
  osEdicao?: OrdemServico | null;
  onClose: () => void;
  onSave: (data: DadosFormOS) => Promise<void>;
}

export const ModalNovaOS: React.FC<Props> = ({ isOpen, clientes, tecnicos, osEdicao, onClose, onSave }) => {
  const [idCliente, setIdCliente] = useState<number>(0);
  const [idTecnico, setIdTecnico] = useState<number>(0);
  const [dataAgendamento, setDataAgendamento] = useState('');
  const [descricaoCliente, setDescricaoCliente] = useState('');
  const [emGarantia, setEmGarantia] = useState(true);
  const [pedido, setPedido] = useState('');
  const [linhas, setLinhas] = useState<LinhaEquipamento[]>(() => [novaLinha()]);
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  const idEdicao = osEdicao?.id_os;
  // O catálogo só é necessário ao criar (na edição os equipamentos são mantidos no detalhe da OS).
  const catalogo = useModelosAtivos(isOpen && !osEdicao);

  useEffect(() => {
    setErroLocal(null);
    limparErro();
    if (osEdicao) {
      setIdCliente(osEdicao.id_cliente);
      setIdTecnico(osEdicao.id_tecnico_atribuido || 0);
      setDataAgendamento(osEdicao.data_agendamento || '');
      setDescricaoCliente(osEdicao.descricao_cliente || '');
      setEmGarantia(osEdicao.em_garantia);
      setPedido(osEdicao.pedido || '');
    } else {
      setIdCliente(0);
      setIdTecnico(0);
      setDataAgendamento('');
      setDescricaoCliente('');
      setEmGarantia(true);
      setPedido('');
    }
    setLinhas([novaLinha()]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, idEdicao]);

  if (!isOpen) return null;

  const clientesAtivos = clientes.filter((c) => c.is_active !== false);
  const tecnicosAtivos = tecnicos.filter((t) => t.is_active !== false && t.role !== 'admin');
  const emEdicao = Boolean(osEdicao);

  // --- Equipamentos (RN-41): cada linha precisa de modelo ativo + série; série única na lista (sem diferenciar maiúsculas) ---
  const contagemSeries = new Map<string, number>();
  linhas.forEach((l) => {
    const k = chaveSerie(l.serie);
    if (k) contagemSeries.set(k, (contagemSeries.get(k) || 0) + 1);
  });
  const serieRepetida = (l: LinhaEquipamento) => (contagemSeries.get(chaveSerie(l.serie)) || 0) > 1;
  const linhaCompleta = (l: LinhaEquipamento) =>
    l.idModelo > 0 && l.serie.trim().length > 0 && l.serie.trim().length <= SERIE_MAX && !serieRepetida(l);
  const equipamentosValidos = linhas.length >= 1 && linhas.every(linhaCompleta);
  const catalogoPronto = catalogo.carregado && !catalogo.carregando && !catalogo.erro && catalogo.modelos.length > 0;

  const atualizarLinha = (chave: number, parcial: Partial<LinhaEquipamento>) =>
    setLinhas((prev) => prev.map((l) => (l.chave === chave ? { ...l, ...parcial } : l)));
  const removerLinha = (chave: number) => setLinhas((prev) => (prev.length > 1 ? prev.filter((l) => l.chave !== chave) : prev));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emEdicao && idCliente <= 0) {
      setErroLocal('Selecione um cliente cadastrado.');
      return;
    }
    if (!descricaoCliente.trim()) {
      setErroLocal('Informe a descrição do problema ou solicitação.');
      return;
    }
    if (!emEdicao) {
      if (!catalogoPronto) {
        setErroLocal('O catálogo de modelos não está disponível. Resolva a pendência na seção "Equipamentos" antes de criar a OS.');
        return;
      }
      if (!equipamentosValidos) {
        setErroLocal(
          'Informe ao menos um equipamento completo (modelo e número de série, sem repetir a série na lista).'
        );
        return;
      }
    }
    setErroLocal(null);

    const ok = await executar(() =>
      onSave({
        id_os: osEdicao?.id_os,
        id_cliente: Number(idCliente),
        id_tecnico_atribuido: Number(idTecnico) > 0 ? Number(idTecnico) : null,
        data_agendamento: dataAgendamento || null,
        descricao_cliente: descricaoCliente,
        em_garantia: emGarantia,
        pedido,
        equipamentos: emEdicao
          ? []
          : linhas.map((l) => ({ id_equipamento_modelo: l.idModelo, numero_serie: l.serie.trim() })),
      })
    );
    if (ok) onClose();
  };

  return (
    <ModalShell
      titulo={osEdicao ? `Editar Ordem de Serviço #${osEdicao.codigo_os}` : 'Nova Ordem de Serviço (OS)'}
      subtitulo={
        osEdicao
          ? 'Edição administrativa: descrição, pedido e garantia'
          : 'Sem técnico a OS nasce "Pendente"; com técnico nasce "Agendado"'
      }
      icone={<Sparkles className="w-5 h-5" />}
      onClose={onClose}
      erro={erro}
      larguraMax="max-w-2xl"
    >
      <form onSubmit={handleSubmit} className="space-y-4 text-xs">
        {erroLocal && (
          <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-600 dark:text-red-400 font-semibold flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{erroLocal}</span>
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="os-cliente" className="block font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
              <Building className="w-3.5 h-3.5 text-primary" /> Cliente solicitante *
            </label>
            {emEdicao ? (
              <p className="w-full bg-secondary/60 border border-border rounded-xl p-3 text-foreground">
                {osEdicao?.cliente.razao_social}
              </p>
            ) : (
              <select
                id="os-cliente"
                value={idCliente}
                onChange={(e) => setIdCliente(Number(e.target.value))}
                className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none cursor-pointer"
              >
                <option value={0}>
                  {clientesAtivos.length === 0 ? 'Nenhum cliente ativo (cadastre um cliente primeiro)' : 'Selecione o cliente...'}
                </option>
                {clientesAtivos.map((c) => (
                  <option key={c.id_cliente} value={c.id_cliente}>
                    {c.razao_social} ({c.cidade}/{c.uf})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label htmlFor="os-tecnico" className="block font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
              <Wrench className="w-3.5 h-3.5 text-primary" /> Técnico responsável (opcional)
            </label>
            {emEdicao ? (
              <p className="w-full bg-secondary/60 border border-border rounded-xl p-3 text-muted-foreground">
                {osEdicao?.tecnico?.nome || 'Sem técnico'} — para trocar, use "Atribuir/Reatribuir técnico".
              </p>
            ) : (
              <select
                id="os-tecnico"
                value={idTecnico}
                onChange={(e) => setIdTecnico(Number(e.target.value))}
                className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none cursor-pointer"
              >
                <option value={0}>Atribuir posteriormente (status: Pendente)</option>
                {tecnicosAtivos.map((t) => (
                  <option key={t.id_tecnico} value={t.id_tecnico}>
                    {t.nome}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="os-data" className="block font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
              <Calendar className="w-3.5 h-3.5 text-primary" /> Data de agendamento
            </label>
            {emEdicao ? (
              <p className="w-full bg-secondary/60 border border-border rounded-xl p-3 text-muted-foreground">
                {osEdicao?.data_agendamento ? formatData(osEdicao.data_agendamento) : 'Não agendado'} — para alterar,
                use "Reagendar" no detalhe da OS.
              </p>
            ) : (
              <input
                id="os-data"
                type="date"
                value={dataAgendamento}
                onChange={(e) => setDataAgendamento(e.target.value)}
                className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none"
              />
            )}
          </div>

          <div>
            <label htmlFor="os-pedido" className="block font-semibold text-foreground mb-1.5">
              Nº do pedido / referência
            </label>
            <input
              id="os-pedido"
              type="text"
              value={pedido}
              onChange={(e) => setPedido(e.target.value)}
              className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none"
            />
          </div>
        </div>

        <div>
          <label htmlFor="os-descricao" className="block font-semibold text-foreground mb-1.5 flex items-center gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 text-primary" /> Descrição do problema / solicitação *
          </label>
          <textarea
            id="os-descricao"
            required
            rows={3}
            placeholder="Descreva a solicitação do cliente, falhas observadas ou objetivos do atendimento..."
            value={descricaoCliente}
            onChange={(e) => setDescricaoCliente(e.target.value)}
            className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none"
          />
        </div>

        {emEdicao ? (
          <p className="text-[11px] text-muted-foreground bg-secondary/50 p-3 rounded-xl border border-border flex items-start gap-2">
            <Package className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>Os equipamentos (modelo e número de série) são mantidos na seção "Equipamentos" do detalhe da OS.</span>
          </p>
        ) : (
          <fieldset className="space-y-3 border border-border rounded-2xl p-4 bg-secondary/20">
            <legend className="px-2 font-semibold text-foreground flex items-center gap-1.5">
              <Package className="w-3.5 h-3.5 text-primary" /> Equipamentos *
            </legend>
            <p className="text-[11px] text-muted-foreground">
              Toda OS precisa de ao menos um equipamento: modelo do catálogo e número de série. O técnico não cadastra nem
              altera equipamentos.
            </p>

            {catalogo.carregando ? (
              <p className="flex items-center gap-2 text-muted-foreground p-3 bg-card border border-border rounded-xl">
                <Loader2 className="w-4 h-4 animate-spin" /> Carregando o catálogo de modelos...
              </p>
            ) : catalogo.erro ? (
              <div role="alert" className="p-3 bg-destructive/10 border border-destructive/30 rounded-xl text-destructive flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <span className="flex items-start gap-2 font-semibold">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" /> {catalogo.erro}
                </span>
                <button
                  type="button"
                  onClick={catalogo.recarregar}
                  className="px-3 py-1.5 bg-destructive text-white rounded-lg font-bold hover:bg-destructive/90 cursor-pointer self-end sm:self-auto"
                >
                  Tentar novamente
                </button>
              </div>
            ) : catalogo.carregado && catalogo.modelos.length === 0 ? (
              <div className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-foreground flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <span className="flex items-start gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
                  <span>
                    Nenhum modelo ativo no catálogo. Cadastre modelos na aba <strong>"Modelos de equipamento"</strong> (menu
                    lateral) e volte para criar a OS.
                  </span>
                </span>
                <button
                  type="button"
                  onClick={catalogo.recarregar}
                  className="px-3 py-1.5 bg-secondary hover:bg-muted border border-border rounded-lg font-bold cursor-pointer self-end sm:self-auto"
                >
                  Recarregar catálogo
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                {linhas.map((l, idx) => {
                  const repetida = serieRepetida(l);
                  return (
                    <div key={l.chave} className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-3 items-start">
                      <div>
                        <label htmlFor={`eq-modelo-${l.chave}`} className="block text-[11px] font-semibold text-muted-foreground mb-1">
                          Modelo {linhas.length > 1 ? `(equipamento ${idx + 1})` : ''}
                        </label>
                        <select
                          id={`eq-modelo-${l.chave}`}
                          value={l.idModelo}
                          onChange={(e) => atualizarLinha(l.chave, { idModelo: Number(e.target.value) })}
                          className="w-full bg-secondary border border-border rounded-xl p-3 text-foreground focus:border-primary focus:outline-none cursor-pointer"
                        >
                          <option value={0}>Selecione o modelo...</option>
                          {catalogo.modelos.map((m) => (
                            <option key={m.id_equipamento_modelo} value={m.id_equipamento_modelo}>
                              {m.modelo}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label htmlFor={`eq-serie-${l.chave}`} className="block text-[11px] font-semibold text-muted-foreground mb-1">
                          Número de série
                        </label>
                        <input
                          id={`eq-serie-${l.chave}`}
                          type="text"
                          maxLength={SERIE_MAX}
                          value={l.serie}
                          onChange={(e) => atualizarLinha(l.chave, { serie: e.target.value })}
                          aria-invalid={repetida ? true : undefined}
                          className={`w-full bg-secondary border rounded-xl p-3 text-foreground focus:outline-none ${
                            repetida ? 'border-destructive focus:border-destructive' : 'border-border focus:border-primary'
                          }`}
                        />
                        {repetida && (
                          <p role="alert" className="text-[11px] text-destructive font-semibold mt-1">
                            Série repetida nesta lista.
                          </p>
                        )}
                      </div>
                      <button
                        type="button"
                        onClick={() => removerLinha(l.chave)}
                        disabled={linhas.length <= 1}
                        aria-label={`Remover equipamento ${idx + 1}`}
                        title={linhas.length <= 1 ? 'A OS precisa de ao menos um equipamento.' : 'Remover este equipamento'}
                        className="sm:mt-5.5 p-3 text-destructive hover:bg-destructive/10 border border-border rounded-xl cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  );
                })}

                <button
                  type="button"
                  onClick={() => setLinhas((prev) => [...prev, novaLinha()])}
                  className="px-3.5 py-2 bg-accent/10 hover:bg-accent/20 text-accent border border-accent/30 rounded-xl font-bold cursor-pointer flex items-center gap-1.5"
                >
                  <Plus className="w-4 h-4" /> Adicionar equipamento
                </button>
              </div>
            )}
          </fieldset>
        )}

        <div className="flex items-center gap-3 bg-secondary/50 p-3 rounded-xl border border-border">
          <input
            type="checkbox"
            id="em_garantia"
            checked={emGarantia}
            onChange={(e) => setEmGarantia(e.target.checked)}
            className="w-4 h-4 accent-primary rounded cursor-pointer"
          />
          <label htmlFor="em_garantia" className="font-semibold text-foreground cursor-pointer flex items-center gap-1.5">
            <ShieldCheck className="w-4 h-4 text-success" /> Atendimento coberto por garantia
          </label>
        </div>

        <div className="pt-4 border-t border-border flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onClose}
            disabled={enviando}
            className="px-4 py-2.5 bg-secondary hover:bg-muted text-muted-foreground hover:text-foreground rounded-xl font-semibold cursor-pointer disabled:opacity-60"
          >
            Cancelar
          </button>
          <button
            type="submit"
            disabled={enviando || (!emEdicao && (!catalogoPronto || !equipamentosValidos))}
            title={
              !emEdicao && (!catalogoPronto || !equipamentosValidos)
                ? 'Informe ao menos um equipamento completo (modelo e número de série).'
                : undefined
            }
            className="px-6 py-2.5 bg-primary hover:bg-primary/90 text-primary-foreground font-bold rounded-xl shadow-md shadow-primary/20 cursor-pointer disabled:opacity-60 flex items-center gap-2"
          >
            {enviando && <Loader2 className="w-4 h-4 animate-spin" />}
            {osEdicao ? 'Salvar alterações' : 'Criar ordem de serviço'}
          </button>
        </div>
      </form>
    </ModalShell>
  );
};
