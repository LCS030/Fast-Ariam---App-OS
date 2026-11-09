import React, { useState } from 'react';
import { OrdemServico, OsEquipamento } from '../types';
import { ChamadoService } from '../services/chamadoService';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';
import { useModelosAtivos } from '../hooks/useModelosAtivos';
import { permissaoEditarEquipamentos } from '../utils/os';
import { ConfirmDialog } from './ConfirmDialog';
import { AlertCircle, Edit2, Info, Loader2, Lock, Package, Plus, Trash2 } from 'lucide-react';

interface Props {
  os: OrdemServico;
  /** Recarrega as listas após vincular/corrigir/remover (o detalhe é derivado da lista). */
  onChanged: () => Promise<void>;
}

const SERIE_MAX = 100;

interface FormEquip {
  idModelo: number;
  serie: string;
}

/**
 * Equipamentos da OS (modelo + série). Edição liberada só até o início do atendimento (RN-45); o servidor é a
 * autoridade e seu `detail` (409/422/404) é exibido como veio. Em OS Finalizada, modelo e série ficam travados (RN-49).
 */
export const SecaoEquipamentosOS: React.FC<Props> = ({ os, onChanged }) => {
  const perm = permissaoEditarEquipamentos(os);
  const equipamentos = os.equipamentos;
  const catalogo = useModelosAtivos(perm.permitido);

  // editando: id do vínculo em edição, 'novo' para inclusão, null = nenhum formulário aberto
  const [editando, setEditando] = useState<number | 'novo' | null>(null);
  const [form, setForm] = useState<FormEquip>({ idModelo: 0, serie: '' });
  const [erroLocal, setErroLocal] = useState<string | null>(null);
  const [aRemover, setARemover] = useState<OsEquipamento | null>(null);
  const { enviando, erro, executar, limparErro } = useAcaoAssincrona();

  const abrirNovo = () => {
    limparErro();
    setErroLocal(null);
    setForm({ idModelo: 0, serie: '' });
    setEditando('novo');
  };

  const abrirEdicao = (eq: OsEquipamento) => {
    limparErro();
    setErroLocal(null);
    setForm({ idModelo: eq.id_equipamento_modelo, serie: eq.numero_serie });
    setEditando(eq.id_os_equipamento);
  };

  const fechar = () => {
    setEditando(null);
    setErroLocal(null);
    limparErro();
  };

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    const serie = form.serie.trim();
    if (form.idModelo <= 0) return setErroLocal('Selecione o modelo do equipamento.');
    if (!serie) return setErroLocal('Informe o número de série.');
    if (serie.length > SERIE_MAX) return setErroLocal(`O número de série aceita no máximo ${SERIE_MAX} caracteres.`);
    const repetida = equipamentos.some(
      (eq) => eq.id_os_equipamento !== editando && eq.numero_serie.trim().toUpperCase() === serie.toUpperCase()
    );
    if (repetida) return setErroLocal('Já existe um equipamento com esta série nesta OS.');
    setErroLocal(null);

    const ok = await executar(async () => {
      if (editando === 'novo') {
        await ChamadoService.vincularEquipamento(os.id_os, { id_equipamento_modelo: form.idModelo, numero_serie: serie });
      } else if (editando !== null) {
        await ChamadoService.corrigirEquipamento(os.id_os, editando, { id_equipamento_modelo: form.idModelo, numero_serie: serie });
      }
      await onChanged();
    });
    if (ok) setEditando(null);
  };

  // Modelos oferecidos: ativos do catálogo + o modelo atual do vínculo em edição, mesmo que tenha sido desativado depois.
  const opcoesModelo = (() => {
    const lista = [...catalogo.modelos];
    if (typeof editando === 'number') {
      const atual = equipamentos.find((eq) => eq.id_os_equipamento === editando);
      if (atual && !lista.some((m) => m.id_equipamento_modelo === atual.id_equipamento_modelo)) {
        lista.push({ id_equipamento_modelo: atual.id_equipamento_modelo, modelo: `${atual.modelo} (inativo)`, is_active: false });
      }
    }
    return lista;
  })();

  const formulario = (
    <form onSubmit={salvar} className="bg-card border border-primary/30 rounded-xl p-3 space-y-3" noValidate>
      {catalogo.carregando ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Carregando o catálogo de modelos...
        </p>
      ) : catalogo.erro ? (
        <div role="alert" className="p-2.5 bg-destructive/10 border border-destructive/30 rounded-lg text-destructive flex items-center justify-between gap-2">
          <span className="font-semibold">{catalogo.erro}</span>
          <button type="button" onClick={catalogo.recarregar} className="px-2.5 py-1 bg-destructive text-white rounded-md font-bold cursor-pointer">
            Tentar novamente
          </button>
        </div>
      ) : catalogo.carregado && catalogo.modelos.length === 0 && editando === 'novo' ? (
        <p className="text-foreground bg-amber-500/10 border border-amber-500/30 rounded-lg p-2.5">
          Nenhum modelo ativo no catálogo. Cadastre modelos na aba "Modelos de equipamento".
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label htmlFor="eqos-modelo" className="block text-[11px] font-semibold text-muted-foreground mb-1">
              Modelo
            </label>
            <select
              id="eqos-modelo"
              value={form.idModelo}
              onChange={(e) => setForm((f) => ({ ...f, idModelo: Number(e.target.value) }))}
              className="w-full bg-secondary border border-border rounded-xl p-2.5 text-foreground focus:border-primary focus:outline-none cursor-pointer"
            >
              <option value={0}>Selecione o modelo...</option>
              {opcoesModelo.map((m) => (
                <option key={m.id_equipamento_modelo} value={m.id_equipamento_modelo}>
                  {m.modelo}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="eqos-serie" className="block text-[11px] font-semibold text-muted-foreground mb-1">
              Número de série
            </label>
            <input
              id="eqos-serie"
              type="text"
              maxLength={SERIE_MAX}
              value={form.serie}
              onChange={(e) => setForm((f) => ({ ...f, serie: e.target.value }))}
              className="w-full bg-secondary border border-border rounded-xl p-2.5 text-foreground focus:border-primary focus:outline-none"
            />
          </div>
        </div>
      )}

      {(erroLocal || erro) && (
        <p role="alert" className="text-destructive font-semibold flex items-start gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {erroLocal || erro}
        </p>
      )}

      <div className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={fechar}
          disabled={enviando}
          className="px-3 py-1.5 bg-secondary hover:bg-muted border border-border rounded-lg font-semibold cursor-pointer disabled:opacity-60"
        >
          Cancelar
        </button>
        <button
          type="submit"
          disabled={enviando || catalogo.carregando || Boolean(catalogo.erro)}
          className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg font-bold cursor-pointer disabled:opacity-60 flex items-center gap-1.5"
        >
          {enviando && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {editando === 'novo' ? 'Vincular equipamento' : 'Salvar'}
        </button>
      </div>
    </form>
  );

  return (
    <div className="bg-secondary/40 p-4 rounded-2xl border border-border space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <span className="text-[11px] font-bold text-accent uppercase tracking-wider flex items-center gap-1.5">
          <Package className="w-3.5 h-3.5" /> Equipamentos da OS ({equipamentos.length})
        </span>
        {perm.permitido && editando === null && (
          <button
            type="button"
            onClick={abrirNovo}
            className="px-3 py-1.5 bg-accent/10 hover:bg-accent/20 text-accent border border-accent/30 rounded-xl font-bold cursor-pointer flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" /> Adicionar equipamento
          </button>
        )}
      </div>

      {!perm.permitido && (
        <p className="text-[11px] text-muted-foreground bg-card p-3 rounded-xl border border-dashed border-border flex items-start gap-2">
          <Lock className="w-3.5 h-3.5 shrink-0 mt-0.5" />
          <span>{perm.motivo}</span>
        </p>
      )}

      {equipamentos.length === 0 ? (
        <div
          role="alert"
          className="p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-foreground flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-amber-600" />
          <span>
            Esta OS não tem equipamento vinculado (registro anterior à regra de equipamento).
            {perm.permitido
              ? ' Vincule ao menos um equipamento: sem ele não é possível atribuir técnico, reagendar nem iniciar o atendimento.'
              : ''}
          </span>
        </div>
      ) : (
        <ul className="space-y-2">
          {equipamentos.map((eq) =>
            editando === eq.id_os_equipamento ? (
              <li key={eq.id_os_equipamento}>{formulario}</li>
            ) : (
              <li
                key={eq.id_os_equipamento}
                className="bg-card p-3 rounded-xl border border-border flex items-center justify-between gap-3 flex-wrap"
              >
                <div className="min-w-0">
                  <p className="font-extrabold text-foreground break-words">{eq.modelo}</p>
                  <p className="text-[11px] text-muted-foreground">
                    Nº de série: <span className="text-accent font-semibold">{eq.numero_serie}</span>
                  </p>
                </div>
                {perm.permitido && editando === null && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => abrirEdicao(eq)}
                      className="px-2.5 py-1.5 bg-secondary hover:bg-muted text-accent border border-border rounded-lg font-semibold flex items-center gap-1 cursor-pointer"
                    >
                      <Edit2 className="w-3.5 h-3.5" /> Corrigir
                    </button>
                    <button
                      type="button"
                      onClick={() => setARemover(eq)}
                      disabled={equipamentos.length <= 1}
                      title={
                        equipamentos.length <= 1
                          ? 'A OS precisa de ao menos um equipamento: não é possível remover o último.'
                          : 'Remover este equipamento da OS'
                      }
                      className="px-2.5 py-1.5 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/30 rounded-lg font-semibold flex items-center gap-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Remover
                    </button>
                  </div>
                )}
              </li>
            )
          )}
        </ul>
      )}

      {editando === 'novo' && formulario}

      {perm.permitido && (
        <p className="text-[10px] text-muted-foreground flex items-start gap-1.5">
          <Info className="w-3 h-3 shrink-0 mt-0.5" />
          <span>
            A edição vale só até o técnico iniciar o atendimento (RN-45). Equipamento com foto, defeito, material ou conserto
            registrado não pode ser removido; o servidor valida cada alteração.
          </span>
        </p>
      )}

      {aRemover && (
        <ConfirmDialog
          titulo="Remover equipamento"
          mensagem={
            <>
              Remover <strong>{aRemover.modelo}</strong> (série <strong>{aRemover.numero_serie}</strong>) desta OS? O registro de
              serviço vazio da visita aberta também é removido.
            </>
          }
          textoConfirmar="Sim, remover"
          onConfirm={async () => {
            await ChamadoService.removerEquipamento(os.id_os, aRemover.id_os_equipamento);
            await onChanged();
          }}
          onClose={() => setARemover(null)}
        />
      )}
    </div>
  );
};
