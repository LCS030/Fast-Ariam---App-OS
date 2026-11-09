// Banco local SQLite (expo-sqlite): cache de OS e filas de envio (SDD 6.12, RNF-09).
// O banco fica no armazenamento privado do app (sandbox do Android). Nenhuma rotina do app
// apaga linhas das filas: eventos/arquivos so mudam de status.
import * as SQLite from "expo-sqlite";

const NOME_BANCO = "fast_ariam_offline.db";
const VERSAO_SCHEMA = 1;

let abrindo: Promise<SQLite.SQLiteDatabase> | null = null;

async function migrar(db: SQLite.SQLiteDatabase): Promise<void> {
  // WAL + synchronous FULL: a gravacao so e confirmada depois de ir ao disco (queda de energia).
  await db.execAsync("PRAGMA journal_mode = WAL;");
  await db.execAsync("PRAGMA synchronous = FULL;");

  const atual = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
  if ((atual?.user_version ?? 0) >= VERSAO_SCHEMA) return;

  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS meta (
      chave TEXT PRIMARY KEY NOT NULL,
      valor TEXT
    );

    -- OS + visitas + servicos (chamado_json) e estado do servidor da visita vigente (estado_json).
    CREATE TABLE IF NOT EXISTS os_cache (
      id_tecnico INTEGER NOT NULL,
      id_os INTEGER NOT NULL,
      chamado_json TEXT NOT NULL,
      estado_json TEXT,
      atualizado_em TEXT NOT NULL,
      PRIMARY KEY (id_tecnico, id_os)
    );

    CREATE TABLE IF NOT EXISTS outbox_eventos (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      client_event_id TEXT NOT NULL UNIQUE,
      id_tecnico INTEGER NOT NULL,
      tipo TEXT NOT NULL,
      id_os INTEGER NOT NULL,
      id_visita INTEGER NOT NULL,
      ocorrido_em TEXT NOT NULL,
      ocorrido_ms INTEGER NOT NULL,
      payload TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pendente',
      codigo TEXT,
      detalhe TEXT,
      tentativas INTEGER NOT NULL DEFAULT 0,
      rotulo_os TEXT,
      criado_ms INTEGER NOT NULL,
      enviado_ms INTEGER,
      tratado INTEGER NOT NULL DEFAULT 0,
      reenvio_de TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_eventos_tecnico_status ON outbox_eventos (id_tecnico, status);
    CREATE INDEX IF NOT EXISTS ix_eventos_os ON outbox_eventos (id_tecnico, id_os);

    CREATE TABLE IF NOT EXISTS outbox_arquivos (
      seq INTEGER PRIMARY KEY AUTOINCREMENT,
      client_file_id TEXT NOT NULL UNIQUE,
      id_tecnico INTEGER NOT NULL,
      tipo_arquivo TEXT NOT NULL,
      caminho_local TEXT,
      mime TEXT NOT NULL,
      id_os INTEGER NOT NULL,
      id_visita INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pendente',
      codigo TEXT,
      detalhe TEXT,
      url TEXT,
      tentativas INTEGER NOT NULL DEFAULT 0,
      criado_ms INTEGER NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_arquivos_tecnico_status ON outbox_arquivos (id_tecnico, status);
  `);
  await db.execAsync(`PRAGMA user_version = ${VERSAO_SCHEMA};`);
}

/** Abre (uma unica vez) e migra o banco. Todas as operacoes passam por aqui. */
export function getDb(): Promise<SQLite.SQLiteDatabase> {
  if (!abrindo) {
    abrindo = (async () => {
      const db = await SQLite.openDatabaseAsync(NOME_BANCO);
      await migrar(db);
      return db;
    })().catch((e) => {
      abrindo = null; // permite nova tentativa
      throw e;
    });
  }
  return abrindo;
}

export async function lerMeta(chave: string): Promise<string | null> {
  const db = await getDb();
  const r = await db.getFirstAsync<{ valor: string | null }>(
    "SELECT valor FROM meta WHERE chave = ?",
    chave
  );
  return r?.valor ?? null;
}

export async function gravarMeta(chave: string, valor: string): Promise<void> {
  const db = await getDb();
  await db.runAsync(
    "INSERT INTO meta (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
    chave,
    valor
  );
}
