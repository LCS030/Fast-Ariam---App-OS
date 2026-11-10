import React, { useCallback, useEffect, useRef, useState } from 'react';
import { FotoServico, MaterialUtilizado, OrdemServico, ServicoEquipamento, Visita } from '../types';
import { ChamadoService } from '../services/chamadoService';
import { useAcaoAssincrona } from '../hooks/useAcaoAssincrona';
import { ConfirmDialog } from './ConfirmDialog';
import { formatData, formatMoeda, mensagemErro } from '../utils/os';
import { FotoSegura } from './FotoSegura';
import { AlertCircle, ArrowRight, CheckCircle2, ImagePlus, Info, Loader2, Plus, Save, Trash2, Wrench, ZoomIn } from 'lucide-react';

/** Resultado do recálculo do custo após corrigir materiais (SDD 6.13). */
export interface AjusteCusto {
  anterior: number | null;
  novo: number;
}

interface Props {
  os: OrdemServico;
  ajusteCusto: AjusteCusto | null;
  /** Recarrega GET /custos e devolve o total anterior → novo; chamado após cada correção de materiais. */
  onMateriaisCorrigidos: () => Promise<void>;
  /** Recarrega as listas (galerias e materiais exibidos no restante do detalhe). */
  onChanged: () => Promise<void>;
  onAbrirFoto: (titulo: string, url: string) => void;
}

const TAMANHO_MAX = 15 * 1024 * 1024;
const ROTULO_TIPO = { defeito: 'defeito', conserto: 'conserto' } as const;
type Tipo = keyof typeof ROTULO_TIPO;

/** Dimensões da imagem no navegador (RN-21: conserto exige menor lado ≥ 960 e maior lado ≥ 1280). */
function lerDimensoes(arquivo: File): Promise<{ w: number; h: number } | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(arquivo);
    const img = new Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}

async function validarArquivo(arquivo: File, tipo: Tipo): Promise<string | null> {
  if (!['image/jpeg', 'image/png'].includes(arquivo.type)) return 'Formato não permitido: envie uma imagem JPEG ou PNG.';
  if (arquivo.size === 0) return 'O arquivo de imagem está vazio.';
  if (arquivo.size > TAMANHO_MAX) return 'A imagem excede o limite de 15 MB.';
  if (tipo === 'conserto') {
    const dim = await lerDimensoes(arquivo);
    if (!dim) return 'Não foi possível ler a imagem selecionada.';
    if (Math.min(dim.w, dim.h) < 960 || Math.max(dim.w, dim.h) < 1280) {
      return `A foto de conserto precisa ter ao menos 960 × 1280 px (em qualquer orientação); a selecionada tem ${dim.w} × ${dim.h} px.`;
    }
  }
  return null;
}

interface LinhaMaterial {
  chave: number;
  nome: string;
  quantidade: string;
  valor: string;
}

let proximaChave = 1;
const paraLinhas = (materiais: MaterialUtilizado[] | undefined): LinhaMaterial[] =>
  (materiais || []).map((m) => ({
    chave: proximaChave++,
    nome: m.nome,
    quantidade: String(m.quantidade),
    valor: String(m.valor),
  }));

const numero = (txt: string) => Number(txt.trim().replace(',', '.'));

const ServicoCorrecao: React.FC<{
  os: OrdemServico;
  visita: Visita;
  servico: ServicoEquipamento;
  rotulo: string;
  onMateriaisCorrigidos: () => Promise<void>;
  onChanged: () => Promise<void>;
  onAbrirFoto: (titulo: string, url: string) => void;
}> = ({ os, visita, servico, rotulo, onMateriaisCorrigidos, onChanged, onAbrirFoto }) => {
  const idServico = servico.id_servico as number;

  // --- Fotos (com id, via GET .../fotos) ---
  const [fotos, setFotos] = useState<{ defeito: FotoServico[]; conserto: FotoServico[] } | null>(null);
  const [erroFotos, setErroFotos] = useState<string | null>(null);
  const [carregandoFotos, setCarregandoFotos] = useState(true);
  const [aviso, setAviso] = useState<string | null>(null);
  const [fotoARemover, setFotoARemover] = useState<FotoServico | null>(null);
  const fotoOp = useAcaoAssincrona();
  const entradaDefeito = useRef<HTMLInputElement>(null);
  const entradaConserto = useRef<HTMLInputElement>(null);

  const carregarFotos = useCallback(async () => {
    setCarregandoFotos(true);
    setErroFotos(null);
    try {
      const r = await ChamadoService.listarFotosServico(os.id_os, visita.id_visita, idServico);
      setFotos({ defeito: r.fotos_defeito || [], conserto: r.fotos_conserto || [] });
    } catch (e) {
      setFotos(null);
      setErroFotos(mensagemErro(e, 'Não foi possível carregar as fotos do equipamento.'));
    } finally {
      setCarregandoFotos(false);
    }
  }, [os.id_os, visita.id_visita, idServico]);

  useEffect(() => {
    carregarFotos();
  }, [carregarFotos]);

  const enviarFoto = async (tipo: Tipo, arquivo: File | undefined) => {
    if (!arquivo) return;
    setAviso(null);
    fotoOp.limparErro();
    const ok = await fotoOp.executar(async () => {
      const problema = await validarArquivo(arquivo, tipo);
      if (problema) throw new Error(problema);
      await ChamadoService.enviarFotoCorrecao(os.id_os, visita.id_visita, idServico, tipo, arquivo);
      await carregarFotos();
      await onChanged();
    });
    if (ok) setAviso(`Foto de ${ROTULO_TIPO[tipo]} enviada.`);
  };

  // --- Materiais ---
  const [linhas, setLinhas] = useState<LinhaMaterial[]>(() => paraLinhas(servico.materiais_utilizados));
  const [erroMat, setErroMat] = useState<string | null>(null);
  const [avisoMat, setAvisoMat] = useState<string | null>(null);
  const matOp = useAcaoAssincrona();
  const materiaisOriginais = JSON.stringify(
    (servico.materiais_utilizados || []).map((m) => [m.nome, Number(m.quantidade), Number(m.valor)])
  );

  // Ressincroniza com o servidor quando a lista é recarregada (sem sobrescrever edição em andamento do mesmo conteúdo).
  const origemRef = useRef(materiaisOriginais);
  useEffect(() => {
    if (origemRef.current !== materiaisOriginais) {
      origemRef.current = materiaisOriginais;
      setLinhas(paraLinhas(servico.materiais_utilizados));
    }
  }, [materiaisOriginais, servico.materiais_utilizados]);

  const atual = JSON.stringify(linhas.map((l) => [l.nome.trim(), numero(l.quantidade), numero(l.valor)]));
  const alterado = atual !== materiaisOriginais;

  const salvarMateriais = async () => {
    setErroMat(null);
    setAvisoMat(null);
    const materiais: MaterialUtilizado[] = [];
    for (const [i, l] of linhas.entries()) {
      const nome = l.nome.trim();
      const qtd = numero(l.quantidade);
      const valor = numero(l.valor);
      const n = i + 1;
      if (!nome || nome.length > 100) return setErroMat(`Material ${n}: informe o nome (1 a 100 caracteres).`);
      if (l.quantidade.trim() === '' || !Number.isInteger(qtd) || qtd < 0)
        return setErroMat(`Material ${n}: a quantidade deve ser um número inteiro maior ou igual a zero.`);
      if (l.valor.trim() === '' || !Number.isFinite(valor) || valor < 0)
        return setErroMat(`Material ${n}: o valor unitário deve ser um número maior ou igual a zero.`);
      materiais.push({ nome, quantidade: qtd, valor });
    }
    const ok = await matOp.executar(async () => {
      await ChamadoService.corrigirMateriais(os.id_os, visita.id_visita, idServico, materiais);
      await onMateriaisCorrigidos();
      await onChanged();
    });
    if (ok) setAvisoMat('Materiais corrigidos e custo recalculado.');
  };

  const bloco = (tipo: Tipo, titulo: string, entrada: React.RefObject<HTMLInputElement>) => {
    const lista = fotos ? fotos[tipo] : [];
    const ultima = lista.length <= 1;
    return (
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider">
            {titulo} ({lista.length})
          </span>
          <button
            type="button"
            disabled={fotoOp.enviando || carregandoFotos}
            onClick={() => entrada.current?.click()}
            className="px-2.5 py-1.5 bg-accent/10 hover:bg-accent/20 text-accent border border-accent/30 rounded-lg font-bold flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            {fotoOp.enviando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <ImagePlus className="w-3.5 h-3.5" />}
            Enviar nova foto de {ROTULO_TIPO[tipo]}
          </button>
          <input
            ref={entrada}
            type="file"
            accept="image/jpeg,image/png"
            className="hidden"
            aria-label={`Selecionar foto de ${ROTULO_TIPO[tipo]}`}
            onChange={(e) => {
              const arquivo = e.target.files?.[0];
              e.target.value = '';
              enviarFoto(tipo, arquivo);
            }}
          />
        </div>
        {lista.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">Nenhuma foto registrada.</p>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {lista.map((f, k) => (
              <div key={f.id_foto} className="bg-card border border-border rounded-xl p-2 space-y-1.5">
                <button
                  type="button"
                  onClick={() => onAbrirFoto(`${titulo} ${k + 1} • ${rotulo}`, f.url)}
                  className="group relative block w-full aspect-video rounded-lg overflow-hidden bg-secondary border border-border cursor-pointer"
                >
                  <FotoSegura idOs={os.id_os} url={f.url} alt={`${titulo} ${k + 1}`} className="w-full h-full object-cover" />
                  <span className="absolute inset-0 bg-black/30 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity">
                    <ZoomIn className="w-5 h-5" />
                  </span>
                </button>
                <button
                  type="button"
                  onClick={() => setFotoARemover(f)}
                  disabled={ultima || fotoOp.enviando}
                  title={
                    ultima
                      ? `Última foto de ${ROTULO_TIPO[tipo]}: não pode ser removida. Envie a nova antes e depois remova a antiga.`
                      : 'Remover esta foto'
                  }
                  className="w-full px-2 py-1 bg-destructive/10 hover:bg-destructive/20 text-destructive border border-destructive/30 rounded-lg text-[11px] font-semibold flex items-center justify-center gap-1 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <Trash2 className="w-3 h-3" /> Remover
                </button>
              </div>
            ))}
          </div>
        )}
        {lista.length === 1 && (
          <p className="text-[10px] text-muted-foreground">
            Esta é a única foto de {ROTULO_TIPO[tipo]}: para trocá-la, envie a nova e depois remova a antiga.
          </p>
        )}
      </div>
    );
  };

  return (
    <div className="bg-card p-4 rounded-xl border border-border space-y-4">
      <h5 className="font-extrabold text-foreground text-xs flex items-center gap-1.5">
        <Wrench className="w-3.5 h-3.5 text-accent" /> {rotulo}
      </h5>

      {/* Fotos */}
      <div className="space-y-3">
        {carregandoFotos && !fotos ? (
          <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Carregando fotos...
          </p>
        ) : erroFotos ? (
          <div role="alert" className="p-2.5 bg-destructive/10 border border-destructive/30 rounded-lg text-destructive flex items-center justify-between gap-2">
            <span className="font-semibold">{erroFotos}</span>
            <button type="button" onClick={carregarFotos} className="px-2.5 py-1 bg-destructive text-white rounded-md font-bold cursor-pointer">
              Tentar novamente
            </button>
          </div>
        ) : (
          <>
            {bloco('defeito', 'Fotos de defeito', entradaDefeito)}
            {bloco('conserto', 'Fotos de conserto', entradaConserto)}
          </>
        )}
        {fotoOp.erro && (
          <p role="alert" className="text-destructive font-semibold flex items-start gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {fotoOp.erro}
          </p>
        )}
        {aviso && !fotoOp.erro && (
          <p className="text-success-strong font-semibold flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> {aviso}
          </p>
        )}
      </div>

      {/* Materiais */}
      <div className="pt-3 border-t border-border space-y-2">
        <span className="text-[10px] font-bold text-muted-foreground uppercase tracking-wider block">Peças e materiais</span>
        {linhas.length === 0 && <p className="text-[11px] text-muted-foreground">Nenhum material registrado.</p>}
        {linhas.map((l, idx) => (
          <div key={l.chave} className="grid grid-cols-[1fr_5rem_7rem_auto] gap-2 items-center">
            <input
              type="text"
              aria-label={`Nome do material ${idx + 1}`}
              placeholder="Nome"
              maxLength={100}
              value={l.nome}
              onChange={(e) => setLinhas((prev) => prev.map((x) => (x.chave === l.chave ? { ...x, nome: e.target.value } : x)))}
              className="min-w-0 bg-secondary border border-border rounded-lg p-2 text-foreground focus:border-primary focus:outline-none"
            />
            <input
              type="text"
              inputMode="numeric"
              aria-label={`Quantidade do material ${idx + 1}`}
              placeholder="Qtd"
              value={l.quantidade}
              onChange={(e) =>
                setLinhas((prev) => prev.map((x) => (x.chave === l.chave ? { ...x, quantidade: e.target.value.replace(/\D/g, '') } : x)))
              }
              className="min-w-0 bg-secondary border border-border rounded-lg p-2 text-foreground focus:border-primary focus:outline-none"
            />
            <input
              type="text"
              inputMode="decimal"
              aria-label={`Valor unitário do material ${idx + 1}`}
              placeholder="Valor (R$)"
              value={l.valor}
              onChange={(e) =>
                setLinhas((prev) => prev.map((x) => (x.chave === l.chave ? { ...x, valor: e.target.value.replace(/[^\d.,]/g, '') } : x)))
              }
              className="min-w-0 bg-secondary border border-border rounded-lg p-2 text-foreground focus:border-primary focus:outline-none"
            />
            <button
              type="button"
              aria-label={`Remover material ${idx + 1}`}
              onClick={() => setLinhas((prev) => prev.filter((x) => x.chave !== l.chave))}
              className="p-2 text-destructive hover:bg-destructive/10 rounded-lg cursor-pointer"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}

        <div className="flex items-center justify-between gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setLinhas((prev) => [...prev, { chave: proximaChave++, nome: '', quantidade: '1', valor: '' }])}
            className="px-2.5 py-1.5 bg-secondary hover:bg-muted border border-border rounded-lg font-semibold flex items-center gap-1.5 cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" /> Adicionar material
          </button>
          <button
            type="button"
            onClick={salvarMateriais}
            disabled={!alterado || matOp.enviando}
            className="px-4 py-1.5 bg-primary hover:bg-primary/90 text-primary-foreground rounded-lg font-bold flex items-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {matOp.enviando ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            Salvar materiais
          </button>
        </div>
        {(erroMat || matOp.erro) && (
          <p role="alert" className="text-destructive font-semibold flex items-start gap-1.5">
            <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {erroMat || matOp.erro}
          </p>
        )}
        {avisoMat && !erroMat && !matOp.erro && (
          <p className="text-success-strong font-semibold flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5" /> {avisoMat}
          </p>
        )}
      </div>

      {fotoARemover && (
        <ConfirmDialog
          titulo="Remover foto"
          mensagem={<>Remover esta foto de {ROTULO_TIPO[fotoARemover.tipo as Tipo] || fotoARemover.tipo} do equipamento <strong>{rotulo}</strong>? A ação é auditada.</>}
          aviso="O arquivo permanece guardado no armazenamento; só o vínculo com o equipamento é removido."
          textoConfirmar="Sim, remover"
          onConfirm={async () => {
            await ChamadoService.removerFotoCorrecao(os.id_os, visita.id_visita, idServico, fotoARemover);
            await carregarFotos();
            await onChanged();
          }}
          onClose={() => setFotoARemover(null)}
        />
      )}
    </div>
  );
};

/**
 * "Correção administrativa" (RN-49): só com a OS Finalizada e não cancelada, restrita a fotos comprobatórias e materiais.
 * Modelo, série, defeitos, conserto salvo, assinatura, km e horários não são editáveis. O servidor audita e recalcula o custo.
 */
export const CorrecaoAdministrativaOS: React.FC<Props> = ({ os, ajusteCusto, onMateriaisCorrigidos, onChanged, onAbrirFoto }) => {
  const visitas = [...os.visitas].sort((a, b) => a.id_visita - b.id_visita);
  const servicosPorVisita = visitas.map((v, idx) => ({
    visita: v,
    indice: idx + 1,
    servicos: (v.servicos_realizados || []).filter((s) => s.id_servico !== undefined),
  }));
  const total = servicosPorVisita.reduce((acc, v) => acc + v.servicos.length, 0);

  return (
    <div className="space-y-3">
      <p className="text-[11px] text-muted-foreground bg-secondary/40 p-3 rounded-xl border border-border flex items-start gap-2">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>
          Com a OS finalizada só é possível corrigir <strong>fotos de defeito/conserto</strong> e <strong>materiais</strong>. Modelo,
          série, defeitos, conserto salvo, assinatura, km e horários não mudam. Toda correção é auditada. Não é possível remover a
          última foto de um tipo (envie a nova antes e remova a antiga).
        </span>
      </p>

      {ajusteCusto && (
        <div role="status" className="p-3 bg-success/10 border border-success/30 rounded-xl space-y-1">
          <p className="font-bold text-foreground flex items-center gap-2 flex-wrap">
            Custo da OS recalculado:
            {ajusteCusto.anterior !== null ? (
              <>
                <span className="line-through text-muted-foreground">{formatMoeda(ajusteCusto.anterior)}</span>
                <ArrowRight className="w-4 h-4" />
              </>
            ) : null}
            <span className="text-success-strong">{formatMoeda(ajusteCusto.novo)}</span>
          </p>
          <p className="text-[11px] text-muted-foreground">
            O recálculo usa os materiais corrigidos e os valores de referência já congelados na finalização da OS (não a
            configuração global atual).
          </p>
        </div>
      )}

      {total === 0 ? (
        <p className="text-[11px] text-muted-foreground bg-secondary/40 p-4 rounded-2xl border border-border">
          Nenhum registro de serviço por equipamento nesta OS para corrigir.
        </p>
      ) : (
        servicosPorVisita
          .filter((v) => v.servicos.length > 0)
          .map(({ visita, indice, servicos }) => (
            <div key={visita.id_visita} className="space-y-3">
              <h4 className="font-bold text-foreground text-xs uppercase tracking-wider">
                Visita {indice} • {formatData(visita.data_visita)}
              </h4>
              {servicos.map((s) => (
                <ServicoCorrecao
                  key={s.id_servico}
                  os={os}
                  visita={visita}
                  servico={s}
                  rotulo={rotuloServico(s)}
                  onMateriaisCorrigidos={onMateriaisCorrigidos}
                  onChanged={onChanged}
                  onAbrirFoto={onAbrirFoto}
                />
              ))}
            </div>
          ))
      )}
    </div>
  );
};

/** Modelo + série do equipamento do serviço; em registros legados, o texto digitado na época. */
export function rotuloServico(s: ServicoEquipamento): string {
  const modelo = s.modelo || s.nome_equipamento || 'Equipamento sem modelo informado';
  const serie = s.numero_serie || s.numero_serie_atendido;
  return serie ? `${modelo} • série ${serie}` : modelo;
}
