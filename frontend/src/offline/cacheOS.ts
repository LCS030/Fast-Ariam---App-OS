// Cache local das OS (RF-22) e leitura do estado LOCAL (cache do servidor + fila).
import type { Chamado, ServicoEquipamento, Visita } from "@/api/chamado";
import type { EstadoVisita } from "@/api/visitas";
import { escolherVisitaAtual } from "@/utils/visita";
import { getDb, gravarMeta, lerMeta } from "./db";
import { listarEventosDaOs, listarEventosParaOverlay } from "./outbox";
import { getSessao } from "./sessao";
import {
  calcularEstadoLocal,
  despesasLocais,
  DespesasLocais,
  kmIniciaisLocais,
  servicosLocais,
} from "./estadoLocal";
import type { EventoOutbox } from "./tipos";

/** Item de GET /api/sync/minhas-os (SDD 6.12). */
export interface ItemMinhasOs {
  chamado: Chamado;
  estado_visita_vigente: EstadoVisita | null;
}

export interface RespostaMinhasOs {
  sincronizado_em: string;
  os: ItemMinhasOs[];
}

/**
 * Substitui o cache pelo conjunto devolvido (o que nao veio sai do cache: OS cancelada ou
 * reatribuida some da lista). `buscaInicioMs` = instante local em que a requisicao partiu:
 * eventos confirmados depois dele ainda nao estao refletidos neste cache.
 */
export async function substituirCache(
  idTecnico: number,
  resposta: RespostaMinhasOs,
  buscaInicioMs: number
): Promise<void> {
  const db = await getDb();
  const itens = Array.isArray(resposta.os) ? resposta.os : [];
  await db.withExclusiveTransactionAsync(async (txn) => {
    await txn.runAsync("DELETE FROM os_cache WHERE id_tecnico = ?", idTecnico);
    for (const item of itens) {
      if (!item?.chamado || typeof item.chamado.id_os !== "number") continue;
      await txn.runAsync(
        `INSERT INTO os_cache (id_tecnico, id_os, chamado_json, estado_json, atualizado_em)
         VALUES (?, ?, ?, ?, ?)`,
        idTecnico,
        item.chamado.id_os,
        JSON.stringify(item.chamado),
        item.estado_visita_vigente ? JSON.stringify(item.estado_visita_vigente) : null,
        resposta.sincronizado_em
      );
    }
  });
  await gravarMeta("cache_busca_inicio_ms", String(buscaInicioMs));
  await gravarMeta("cache_sincronizado_em", resposta.sincronizado_em);
  await gravarMeta("cache_sincronizado_ms", String(Date.now()));
}

export async function ultimaAtualizacaoCache(): Promise<number | null> {
  const v = await lerMeta("cache_sincronizado_ms");
  return v ? Number(v) : null;
}

interface LinhaCache {
  id_os: number;
  chamado_json: string;
  estado_json: string | null;
}

export interface OsLocal {
  /** Chamado com o status ja ajustado pelas acoes locais. */
  chamado: Chamado;
  /** Visita vigente (a executavel). */
  visita?: Visita;
  /** Mesmos campos de GET .../estado, calculados no aparelho; null = sem visita executavel. */
  estado: EstadoVisita | null;
  servicos: ServicoEquipamento[];
  despesas: DespesasLocais;
  /** KM inicial de cada perna, incluindo o que ainda esta so na fila. */
  kmInicio: { ida: number | null; volta: number | null };
  /** Acoes desta OS ainda nao confirmadas pelo servidor. */
  acoesPendentes: number;
}

function montar(linha: LinhaCache, eventos: EventoOutbox[]): OsLocal | null {
  let chamado: Chamado;
  let base: EstadoVisita | null = null;
  try {
    chamado = JSON.parse(linha.chamado_json) as Chamado;
    base = linha.estado_json ? (JSON.parse(linha.estado_json) as EstadoVisita) : null;
  } catch {
    return null; // linha corrompida: ignora (o proximo sync reconstroi o cache)
  }
  if (base) {
    base = { ...base, equipamentos: Array.isArray(base.equipamentos) ? base.equipamentos : [] };
  }
  const visita = escolherVisitaAtual(chamado.visitas);
  const daOs = eventos.filter((e) => e.id_os === linha.id_os);
  const { status, estado } = calcularEstadoLocal(
    String(chamado.status),
    base,
    visita?.id_visita,
    daOs
  );
  return {
    chamado: { ...chamado, status },
    visita,
    estado,
    servicos: servicosLocais(visita, estado, daOs),
    despesas: despesasLocais(visita, daOs),
    kmInicio: kmIniciaisLocais(visita, daOs),
    acoesPendentes: daOs.filter((e) => e.status === "pendente").length,
  };
}

export async function obterOsLocal(idOs: number): Promise<OsLocal | null> {
  const sessao = await getSessao();
  if (!sessao) return null;
  const db = await getDb();
  const linha = await db.getFirstAsync<LinhaCache>(
    "SELECT id_os, chamado_json, estado_json FROM os_cache WHERE id_tecnico = ? AND id_os = ?",
    sessao.idTecnico,
    idOs
  );
  if (!linha) return null;
  const eventos = await listarEventosParaOverlay(sessao.idTecnico);
  return montar(linha, eventos);
}

export async function listarOsLocal(): Promise<OsLocal[]> {
  const sessao = await getSessao();
  if (!sessao) return [];
  const db = await getDb();
  const linhas = await db.getAllAsync<LinhaCache>(
    "SELECT id_os, chamado_json, estado_json FROM os_cache WHERE id_tecnico = ? ORDER BY id_os DESC",
    sessao.idTecnico
  );
  const eventos = await listarEventosParaOverlay(sessao.idTecnico);
  return linhas
    .map((l) => montar(l, eventos))
    .filter((o): o is OsLocal => o !== null && !o.chamado.is_cancelled);
}

/** Texto curto para identificar a OS nas pendencias, ex.: "OS #PED-1 - Mercado X". */
export async function rotuloDaOs(idTecnico: number, idOs: number): Promise<string> {
  const db = await getDb();
  const l = await db.getFirstAsync<{ chamado_json: string }>(
    "SELECT chamado_json FROM os_cache WHERE id_tecnico = ? AND id_os = ?",
    idTecnico,
    idOs
  );
  try {
    const c = l ? (JSON.parse(l.chamado_json) as Chamado) : null;
    if (c) return `OS #${c.pedido || c.id_os}${c.cliente_nome ? " - " + c.cliente_nome : ""}`;
  } catch {
    // cai no rotulo simples
  }
  return `OS #${idOs}`;
}

/** Acoes registradas para a OS (mais recentes primeiro), com o status de envio de cada uma. */
export async function listarAcoesDaOs(idOs: number, limite = 30): Promise<EventoOutbox[]> {
  const sessao = await getSessao();
  if (!sessao) return [];
  const todas = await listarEventosDaOs(sessao.idTecnico, idOs);
  return todas.slice(-limite).reverse();
}
