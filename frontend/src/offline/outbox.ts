// Operacoes sobre as filas outbox_eventos / outbox_arquivos.
// Regra de ouro (RNF-09): gravar ANTES de enviar; nunca apagar linhas (so mudar status).
import { randomUUID } from "expo-crypto";
import { getDb, lerMeta } from "./db";
import type { ArquivoOutbox, EventoOutbox, StatusFila, TipoArquivo, TipoEvento } from "./tipos";

export const novoUuid = (): string => randomUUID(); // UUID v4

// ---------------------------------------------------------------------------------------------
// Mapeamento de linhas
// ---------------------------------------------------------------------------------------------
type LinhaEvento = Omit<EventoOutbox, "payload" | "tratado"> & { payload: string; tratado: number };

function paraEvento(l: LinhaEvento): EventoOutbox {
  let payload: Record<string, unknown> = {};
  try {
    payload = JSON.parse(l.payload) ?? {};
  } catch {
    payload = {};
  }
  return { ...l, payload, tratado: l.tratado === 1 };
}

// ---------------------------------------------------------------------------------------------
// Gravacao atomica de uma acao (arquivos + eventos na mesma transacao)
// ---------------------------------------------------------------------------------------------
export interface NovoArquivo {
  client_file_id: string;
  tipo_arquivo: TipoArquivo;
  caminho_local: string;
  mime: "image/jpeg" | "image/png";
  id_os: number;
  id_visita: number;
}

export interface NovoEvento {
  client_event_id: string;
  tipo: TipoEvento;
  id_os: number;
  id_visita: number;
  ocorrido_em: string;
  payload: Record<string, unknown>;
  rotulo_os: string | null;
  reenvio_de?: string | null;
}

export async function gravarAcao(
  idTecnico: number,
  arquivos: NovoArquivo[],
  eventos: NovoEvento[]
): Promise<void> {
  const db = await getDb();
  const agora = Date.now();
  await db.withExclusiveTransactionAsync(async (txn) => {
    for (const a of arquivos) {
      await txn.runAsync(
        `INSERT INTO outbox_arquivos
           (client_file_id, id_tecnico, tipo_arquivo, caminho_local, mime, id_os, id_visita, status, criado_ms)
         VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente', ?)`,
        a.client_file_id,
        idTecnico,
        a.tipo_arquivo,
        a.caminho_local,
        a.mime,
        a.id_os,
        a.id_visita,
        agora
      );
    }
    for (let i = 0; i < eventos.length; i++) {
      const e = eventos[i];
      // ocorrido_ms: instante real da acao; +i garante ordem estavel entre eventos da mesma acao.
      const ms = parseIsoMs(e.ocorrido_em, agora) + i;
      await txn.runAsync(
        `INSERT INTO outbox_eventos
           (client_event_id, id_tecnico, tipo, id_os, id_visita, ocorrido_em, ocorrido_ms, payload,
            status, rotulo_os, criado_ms, reenvio_de)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendente', ?, ?, ?)`,
        e.client_event_id,
        idTecnico,
        e.tipo,
        e.id_os,
        e.id_visita,
        e.ocorrido_em,
        ms,
        JSON.stringify(e.payload),
        e.rotulo_os,
        agora,
        e.reenvio_de ?? null
      );
    }
  });
}

function parseIsoMs(iso: string, fallback: number): number {
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : fallback;
}

// ---------------------------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------------------------
const ORDEM_ENVIO = "ORDER BY ocorrido_ms ASC, seq ASC";

export async function listarEventosPendentes(idTecnico: number): Promise<EventoOutbox[]> {
  const db = await getDb();
  const linhas = await db.getAllAsync<LinhaEvento>(
    `SELECT * FROM outbox_eventos WHERE id_tecnico = ? AND status = 'pendente' ${ORDEM_ENVIO}`,
    idTecnico
  );
  return linhas.map(paraEvento);
}

/** Rejeitados ainda nao tratados (para a tela de pendencias) + opcionalmente os ja tratados. */
export async function listarEventosRejeitados(
  idTecnico: number,
  incluirTratados = false
): Promise<EventoOutbox[]> {
  const db = await getDb();
  const linhas = await db.getAllAsync<LinhaEvento>(
    `SELECT * FROM outbox_eventos
      WHERE id_tecnico = ? AND status = 'rejeitado' ${incluirTratados ? "" : "AND tratado = 0"}
      ORDER BY ocorrido_ms DESC, seq DESC`,
    idTecnico
  );
  return linhas.map(paraEvento);
}

/** Eventos que ainda afetam o estado local: pendentes + enviados que o cache ainda nao reflete. */
export async function listarEventosParaOverlay(idTecnico: number): Promise<EventoOutbox[]> {
  const db = await getDb();
  const desde = Number((await lerMeta("cache_busca_inicio_ms")) ?? 0);
  const linhas = await db.getAllAsync<LinhaEvento>(
    `SELECT * FROM outbox_eventos
      WHERE id_tecnico = ?
        AND (status = 'pendente' OR (status = 'enviado' AND enviado_ms > ?))
      ${ORDEM_ENVIO}`,
    idTecnico,
    desde
  );
  return linhas.map(paraEvento);
}

export async function listarEventosDaOs(idTecnico: number, idOs: number): Promise<EventoOutbox[]> {
  const db = await getDb();
  const linhas = await db.getAllAsync<LinhaEvento>(
    `SELECT * FROM outbox_eventos WHERE id_tecnico = ? AND id_os = ? ${ORDEM_ENVIO}`,
    idTecnico,
    idOs
  );
  return linhas.map(paraEvento);
}

export async function obterEvento(clientEventId: string): Promise<EventoOutbox | null> {
  const db = await getDb();
  const l = await db.getFirstAsync<LinhaEvento>(
    "SELECT * FROM outbox_eventos WHERE client_event_id = ?",
    clientEventId
  );
  return l ? paraEvento(l) : null;
}

export async function atualizarEvento(
  clientEventId: string,
  campos: {
    status?: StatusFila;
    codigo?: string | null;
    detalhe?: string | null;
    enviado_ms?: number | null;
    tratado?: boolean;
    somarTentativa?: boolean;
  }
): Promise<void> {
  const db = await getDb();
  const sets: string[] = [];
  const params: (string | number | null)[] = [];
  if (campos.status !== undefined) {
    sets.push("status = ?");
    params.push(campos.status);
  }
  if (campos.codigo !== undefined) {
    sets.push("codigo = ?");
    params.push(campos.codigo);
  }
  if (campos.detalhe !== undefined) {
    sets.push("detalhe = ?");
    params.push(campos.detalhe);
  }
  if (campos.enviado_ms !== undefined) {
    sets.push("enviado_ms = ?");
    params.push(campos.enviado_ms);
  }
  if (campos.tratado !== undefined) {
    sets.push("tratado = ?");
    params.push(campos.tratado ? 1 : 0);
  }
  if (campos.somarTentativa) sets.push("tentativas = tentativas + 1");
  if (sets.length === 0) return;
  params.push(clientEventId);
  await db.runAsync(`UPDATE outbox_eventos SET ${sets.join(", ")} WHERE client_event_id = ?`, params);
}

// ---------------------------------------------------------------------------------------------
// Arquivos
// ---------------------------------------------------------------------------------------------
export async function listarArquivosPendentes(idTecnico: number): Promise<ArquivoOutbox[]> {
  const db = await getDb();
  return db.getAllAsync<ArquivoOutbox>(
    `SELECT * FROM outbox_arquivos WHERE id_tecnico = ? AND status = 'pendente' ORDER BY seq ASC`,
    idTecnico
  );
}

export async function obterArquivos(ids: string[]): Promise<ArquivoOutbox[]> {
  if (ids.length === 0) return [];
  const db = await getDb();
  const marcas = ids.map(() => "?").join(",");
  return db.getAllAsync<ArquivoOutbox>(
    `SELECT * FROM outbox_arquivos WHERE client_file_id IN (${marcas})`,
    ids
  );
}

export async function atualizarArquivo(
  clientFileId: string,
  campos: {
    status?: StatusFila;
    codigo?: string | null;
    detalhe?: string | null;
    url?: string | null;
    caminho_local?: string | null;
    somarTentativa?: boolean;
  }
): Promise<void> {
  const db = await getDb();
  const sets: string[] = [];
  const params: (string | number | null)[] = [];
  for (const k of ["status", "codigo", "detalhe", "url", "caminho_local"] as const) {
    if (campos[k] !== undefined) {
      sets.push(`${k} = ?`);
      params.push(campos[k] as string | null);
    }
  }
  if (campos.somarTentativa) sets.push("tentativas = tentativas + 1");
  if (sets.length === 0) return;
  params.push(clientFileId);
  await db.runAsync(`UPDATE outbox_arquivos SET ${sets.join(", ")} WHERE client_file_id = ?`, params);
}

/** Arquivos ja confirmados que ainda ocupam espaco no aparelho. */
export async function listarArquivosLiberaveis(idTecnico: number): Promise<ArquivoOutbox[]> {
  const db = await getDb();
  return db.getAllAsync<ArquivoOutbox>(
    `SELECT * FROM outbox_arquivos
      WHERE id_tecnico = ? AND status = 'enviado' AND caminho_local IS NOT NULL`,
    idTecnico
  );
}

/** Algum evento ainda nao concluido (pendente ou rejeitado nao tratado) referencia o arquivo? */
export async function arquivoEmUso(clientFileId: string): Promise<boolean> {
  const db = await getDb();
  const r = await db.getFirstAsync<{ n: number }>(
    `SELECT COUNT(*) AS n FROM outbox_eventos
      WHERE (status = 'pendente' OR (status = 'rejeitado' AND tratado = 0))
        AND payload LIKE ?`,
    `%${clientFileId}%`
  );
  return (r?.n ?? 0) > 0;
}

// ---------------------------------------------------------------------------------------------
// Contagens (indicador global)
// ---------------------------------------------------------------------------------------------
export async function contarFila(idTecnico: number) {
  const db = await getDb();
  const e = await db.getFirstAsync<{ pendentes: number; rejeitadas: number }>(
    `SELECT
       COALESCE(SUM(CASE WHEN status = 'pendente' THEN 1 ELSE 0 END), 0) AS pendentes,
       COALESCE(SUM(CASE WHEN status = 'rejeitado' AND tratado = 0 THEN 1 ELSE 0 END), 0) AS rejeitadas
     FROM outbox_eventos WHERE id_tecnico = ?`,
    idTecnico
  );
  const a = await db.getFirstAsync<{ n: number }>(
    `SELECT COUNT(*) AS n FROM outbox_arquivos WHERE id_tecnico = ? AND status = 'pendente'`,
    idTecnico
  );
  return {
    pendentes: e?.pendentes ?? 0,
    rejeitadas: e?.rejeitadas ?? 0,
    arquivosPendentes: a?.n ?? 0,
  };
}
