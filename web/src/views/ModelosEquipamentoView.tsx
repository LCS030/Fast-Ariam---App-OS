import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { EquipamentoModelo } from '../types';
import { ChamadoService } from '../services/chamadoService';
import { ModalModeloEquipamento } from '../components/ModalModeloEquipamento';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { mensagemErro } from '../utils/os';
import { AlertTriangle, Edit2, Filter, Loader2, Package, Plus, Power, Search, UserCheck, UserX, X } from 'lucide-react';

type FiltroSituacao = 'ATIVOS' | 'INATIVOS' | 'TODOS';

/**
 * Catálogo de modelos de equipamento (SDD 6.13 / RF-23). Só o nome; DELETE = desativação lógica; reativar = PATCH.
 * Carrega a própria lista (todos os modelos) na abertura da aba: em falha mostra erro + "Tentar novamente", nunca lista fictícia.
 */
export const ModelosEquipamentoView: React.FC = () => {
  const [modelos, setModelos] = useState<EquipamentoModelo[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [erroAcao, setErroAcao] = useState<string | null>(null);

  const [busca, setBusca] = useState('');
  const [filtro, setFiltro] = useState<FiltroSituacao>('ATIVOS');

  const [modalAberto, setModalAberto] = useState(false);
  const [modeloEdicao, setModeloEdicao] = useState<EquipamentoModelo | null>(null);
  const [modeloParaDesativar, setModeloParaDesativar] = useState<EquipamentoModelo | null>(null);
  const [reativandoId, setReativandoId] = useState<number | null>(null);

  const cargaAtual = useRef(0);

  const carregar = useCallback(async () => {
    const id = ++cargaAtual.current;
    setCarregando(true);
    setErroCarga(null);
    try {
      const lista = await ChamadoService.listarModelos();
      if (id !== cargaAtual.current) return;
      setModelos(Array.isArray(lista) ? lista : []);
    } catch (e) {
      if (id !== cargaAtual.current) return;
      setModelos([]);
      setErroCarga(mensagemErro(e, 'Não foi possível carregar os modelos de equipamento.'));
    } finally {
      if (id === cargaAtual.current) setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const abrirNovo = () => {
    setModeloEdicao(null);
    setModalAberto(true);
  };

  const abrirEdicao = (m: EquipamentoModelo) => {
    setModeloEdicao(m);
    setModalAberto(true);
  };

  const fecharModal = () => {
    setModalAberto(false);
    setModeloEdicao(null);
  };

  const salvar = async (nome: string) => {
    if (modeloEdicao) await ChamadoService.renomearModelo(modeloEdicao.id_equipamento_modelo, nome);
    else await ChamadoService.criarModelo(nome);
    await carregar();
  };

  const reativar = async (m: EquipamentoModelo) => {
    setErroAcao(null);
    setReativandoId(m.id_equipamento_modelo);
    try {
      await ChamadoService.reativarModelo(m.id_equipamento_modelo);
      await carregar();
    } catch (e) {
      setErroAcao(`Não foi possível reativar o modelo: ${mensagemErro(e)}`);
    } finally {
      setReativandoId(null);
    }
  };

  const contagem = useMemo(
    () => ({
      ATIVOS: modelos.filter((m) => m.is_active !== false).length,
      INATIVOS: modelos.filter((m) => m.is_active === false).length,
      TODOS: modelos.length,
    }),
    [modelos]
  );

  const termo = busca.trim().toLowerCase();
  const filtrados = useMemo(
    () =>
      modelos
        .filter((m) => {
          if (termo && !m.modelo.toLowerCase().includes(termo)) return false;
          const ativo = m.is_active !== false;
          if (filtro === 'ATIVOS') return ativo;
          if (filtro === 'INATIVOS') return !ativo;
          return true;
        })
        .sort((a, b) => a.modelo.localeCompare(b.modelo, 'pt-BR', { sensitivity: 'base' })),
    [modelos, termo, filtro]
  );

  return (
    <div className="surface-card p-6 shadow-sm space-y-6">
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-foreground font-['Space_Grotesk'] flex items-center gap-2">
            <Package className="w-5 h-5 text-accent" /> Modelos de equipamento
          </h2>
          <p className="text-xs text-muted-foreground">
            Catálogo usado para vincular modelo e número de série às ordens de serviço
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
            <input
              type="text"
              aria-label="Buscar modelo"
              placeholder="Buscar por nome do modelo..."
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="w-full bg-secondary border border-border rounded-xl py-2 pl-9 pr-3 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="button"
            onClick={abrirNovo}
            className="py-2 px-4 bg-accent hover:bg-accent/90 text-white font-extrabold text-xs rounded-xl shadow-md flex items-center gap-1.5 cursor-pointer whitespace-nowrap"
          >
            <Plus className="w-4 h-4" />
            <span>Novo modelo</span>
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 p-1.5 bg-secondary/50 rounded-2xl border border-border w-fit text-xs">
        <span className="text-[11px] font-bold text-muted-foreground px-2 flex items-center gap-1">
          <Filter className="w-3.5 h-3.5" /> Situação:
        </span>
        {(['ATIVOS', 'TODOS', 'INATIVOS'] as FiltroSituacao[]).map((f) => (
          <button
            key={f}
            type="button"
            onClick={() => setFiltro(f)}
            className={`px-3 py-1.5 rounded-xl font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
              filtro === f
                ? f === 'INATIVOS'
                  ? 'bg-amber-500 text-white shadow-xs'
                  : 'bg-primary text-primary-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground hover:bg-secondary'
            }`}
          >
            {f === 'ATIVOS' && <UserCheck className="w-3.5 h-3.5" />}
            {f === 'INATIVOS' && <UserX className="w-3.5 h-3.5" />}
            <span>{f === 'ATIVOS' ? 'Ativos' : f === 'TODOS' ? 'Todos' : 'Inativos'}</span>
            <span className="px-1.5 rounded-full text-[10px] bg-background/20 font-extrabold">{contagem[f]}</span>
          </button>
        ))}
      </div>

      {erroAcao && (
        <div role="alert" className="p-3 bg-destructive/10 border border-destructive/30 rounded-2xl flex items-center justify-between gap-3 text-xs text-destructive">
          <span className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" /> {erroAcao}
          </span>
          <button type="button" onClick={() => setErroAcao(null)} aria-label="Dispensar aviso" className="p-1 cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {carregando ? (
        <div className="p-12 text-center text-muted-foreground bg-secondary/30 rounded-2xl border border-dashed border-border">
          <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin opacity-60" />
          <p className="font-bold text-foreground">Carregando modelos...</p>
        </div>
      ) : erroCarga ? (
        <div role="alert" className="p-8 text-center bg-destructive/5 rounded-2xl border border-destructive/30 space-y-3">
          <AlertTriangle className="w-8 h-8 mx-auto text-destructive" />
          <p className="font-bold text-foreground">Não foi possível carregar os modelos.</p>
          <p className="text-xs text-destructive">{erroCarga}</p>
          <button
            type="button"
            onClick={carregar}
            className="px-4 py-2 bg-destructive text-white rounded-xl text-xs font-bold hover:bg-destructive/90 cursor-pointer"
          >
            Tentar novamente
          </button>
        </div>
      ) : filtrados.length === 0 ? (
        <div className="p-12 text-center text-muted-foreground bg-secondary/30 rounded-2xl border border-dashed border-border">
          <Package className="w-10 h-10 mx-auto mb-2 opacity-50" />
          <p className="font-bold text-foreground">
            {modelos.length === 0
              ? 'Nenhum modelo cadastrado.'
              : termo
              ? 'Nenhum modelo encontrado para esta busca.'
              : filtro === 'INATIVOS'
              ? 'Nenhum modelo inativo.'
              : 'Nenhum modelo ativo.'}
          </p>
          {modelos.length === 0 && (
            <p className="text-xs mt-1">Cadastre os modelos com "Novo modelo": eles são necessários para criar ordens de serviço.</p>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtrados.map((m) => {
            const ativo = m.is_active !== false;
            const reativando = reativandoId === m.id_equipamento_modelo;
            return (
              <div
                key={m.id_equipamento_modelo}
                className={`bg-card border rounded-2xl p-5 space-y-4 transition-all flex flex-col justify-between shadow-sm ${
                  ativo ? 'border-border hover:border-accent/40' : 'border-amber-500/30 bg-amber-500/5'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-sm font-extrabold text-foreground break-words min-w-0">{m.modelo}</h3>
                  {ativo ? (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-success/10 text-success-strong border border-success/20 shrink-0">
                      <UserCheck className="w-3 h-3" /> Ativo
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/10 text-amber-500 border border-amber-500/20 shrink-0">
                      <UserX className="w-3 h-3" /> Inativo
                    </span>
                  )}
                </div>

                <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
                  <button
                    type="button"
                    onClick={() => abrirEdicao(m)}
                    className="px-3 py-1.5 bg-secondary hover:bg-muted text-accent border border-border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors"
                  >
                    <Edit2 className="w-3.5 h-3.5" /> Editar
                  </button>
                  <button
                    type="button"
                    disabled={reativando}
                    onClick={() => (ativo ? setModeloParaDesativar(m) : reativar(m))}
                    className={`px-3 py-1.5 border rounded-xl text-xs font-semibold flex items-center gap-1 cursor-pointer transition-colors disabled:opacity-60 ${
                      ativo
                        ? 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-500 border-amber-500/30'
                        : 'bg-success/10 hover:bg-success/20 text-success-strong border-success/30'
                    }`}
                  >
                    {reativando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}
                    <span>{ativo ? 'Desativar' : 'Reativar'}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {modalAberto && <ModalModeloEquipamento modeloEdicao={modeloEdicao} onClose={fecharModal} onSave={salvar} />}

      {modeloParaDesativar && (
        <ConfirmDialog
          titulo="Desativar modelo"
          mensagem={
            <>
              Desativar o modelo <strong>{modeloParaDesativar.modelo}</strong>? Ele deixa de poder ser escolhido em novas OS;
              as OS e os equipamentos já vinculados continuam com o modelo (desativação lógica, pode ser reativado).
            </>
          }
          textoConfirmar="Sim, desativar"
          onConfirm={async () => {
            await ChamadoService.desativarModelo(modeloParaDesativar.id_equipamento_modelo);
            await carregar();
          }}
          onClose={() => setModeloParaDesativar(null)}
        />
      )}
    </div>
  );
};
