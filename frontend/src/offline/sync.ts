// Motor de sincronizacao (SDD 6.12): arquivos -> eventos -> cache de OS.
//
// Garantias:
//  - Nada e apagado: eventos/arquivos so mudam de status (RNF-09).
//  - Reenvio idempotente: client_event_id / client_file_id sao reutilizados ate a confirmacao.
//  - Uma rejeicao nunca trava a fila (resultado por evento).
//  - 401: fila preservada, novo login online exigido antes de sincronizar (RN-39).
import NetInfo from "@react-native-community/netinfo";
import { AppState } from "react-native";
import { isAxiosError } from "axios";
import api, { API_BASE_URL } from "@/api/api";
import { anexarImagem, UPLOAD_TIMEOUT_MS } from "@/api/arquivo";
import { agoraIso } from "@/api/visitas";
import { getErrorMessage } from "@/utils/alerts";
import { arquivoExiste, removerArquivoLocal } from "./arquivos";
import { substituirCache, ultimaAtualizacaoCache, RespostaMinhasOs } from "./cacheOS";
import { gravarMeta, lerMeta } from "./db";
import { sha256DoArquivo } from "./hash";
import {
  arquivoEmUso,
  atualizarArquivo,
  atualizarEvento,
  listarArquivosLiberaveis,
  listarArquivosPendentes,
  listarEventosPendentes,
  novoUuid,
  obterArquivos,
} from "./outbox";
import { avaliarSessao, marcarJwtRejeitado } from "./sessao";
import { atualizarContagens } from "./status";
import { atualizarStatus, getStatus } from "./store";
import { ArquivoOutbox, EventoOutbox, refsDoPayload } from "./tipos";

const MAX_EVENTOS_POR_LOTE = 200;
const INTERVALO_BASE_MS = 60_000; // verificacao periodica
const BACKOFF_INICIAL_MS = 15_000;
const BACKOFF_MAXIMO_MS = 5 * 60_000;
/** Reenvios de um arquivo cujo hash divergiu no servidor antes de marca-lo como rejeitado (nunca e descartado). */
const MAX_TENTATIVAS_HASH_DIVERGENTE = 5;
const REFRESH_CACHE_MS = 5 * 60_000; // atualiza o cache de OS ao menos a cada 5 min online

export type MotivoSync = "ok" | "ocupado" | "offline" | "sem_sessao" | "login_necessario" | "erro";

export interface ResultadoSync {
  ok: boolean;
  motivo: MotivoSync;
  mensagem?: string;
}

class ErroAutenticacao extends Error {}

let emAndamento: Promise<ResultadoSync> | null = null;
let repetir = false;
let falhasSeguidas = 0;
let proximaTentativaEm = 0;
let timer: ReturnType<typeof setTimeout> | null = null;

// ---------------------------------------------------------------------------------------------
// Conexao
// ---------------------------------------------------------------------------------------------
function estaOnline(s: { isConnected: boolean | null; isInternetReachable: boolean | null }): boolean {
  return s.isConnected !== false && s.isInternetReachable !== false;
}

async function dispositivoId(): Promise<string> {
  let id = await lerMeta("dispositivo_id");
  if (!id) {
    id = novoUuid();
    await gravarMeta("dispositivo_id", id);
  }
  return id;
}

// ---------------------------------------------------------------------------------------------
// Classificacao de erros HTTP
// ---------------------------------------------------------------------------------------------
/** 4xx que repetir nao resolve (exceto 401/408/429). */
function erroDefinitivo(err: unknown): boolean {
  if (!isAxiosError(err) || !err.response) return false;
  const s = err.response.status;
  return s >= 400 && s < 500 && s !== 401 && s !== 408 && s !== 429;
}

/** `codigo` estavel devolvido pela API no corpo do erro (ex.: HASH_DIVERGENTE). */
function codigoDoErro(err: unknown): string | undefined {
  if (!isAxiosError(err)) return undefined;
  const dados = err.response?.data as { codigo?: unknown } | undefined;
  return typeof dados?.codigo === "string" ? dados.codigo : undefined;
}

function eh401(err: unknown): boolean {
  return isAxiosError(err) && err.response?.status === 401;
}

// ---------------------------------------------------------------------------------------------
// Passo 1: arquivos
// ---------------------------------------------------------------------------------------------
async function enviarArquivos(idTecnico: number): Promise<string | null> {
  const pendentes = await listarArquivosPendentes(idTecnico);
  let falha: string | null = null;

  for (const a of pendentes) {
    if (!a.caminho_local || !(await arquivoExiste(a.caminho_local))) {
      // Nao ha o que reenviar: registra de forma rastreavel (nunca silencioso).
      await atualizarArquivo(a.client_file_id, {
        status: "rejeitado",
        codigo: "ARQUIVO_LOCAL_AUSENTE",
        detalhe: "O arquivo não foi encontrado no aparelho.",
      });
      continue;
    }

    // Integridade: o hash foi calculado na CAPTURA (fila). Arquivos enfileirados por uma versao antiga do app nao
    // o tem; para eles calcula-se agora (protege so o transito) e persiste-se.
    let sha256 = a.sha256;
    if (!sha256) {
      try {
        sha256 = await sha256DoArquivo(a.caminho_local);
        await atualizarArquivo(a.client_file_id, { sha256 });
      } catch {
        sha256 = null; // nao conseguiu ler para calcular: envia sem hash (o servidor grava o proprio)
      }
    }

    const form = new FormData();
    form.append("client_file_id", a.client_file_id);
    form.append("tipo_arquivo", a.tipo_arquivo);
    form.append("id_os", String(a.id_os));
    form.append("id_visita", String(a.id_visita));
    if (sha256) form.append("sha256", sha256);
    anexarImagem(form, "file", { uri: a.caminho_local, mime: a.mime }, a.tipo_arquivo);

    try {
      const res = await api.post<{ url?: string; resultado?: string }>("/sync/arquivos", form, {
        headers: { "Content-Type": "multipart/form-data" },
        timeout: UPLOAD_TIMEOUT_MS,
        semRedirecionarLogin: true,
      });
      await atualizarArquivo(a.client_file_id, {
        status: "enviado",
        url: res.data?.url ?? null,
        codigo: null,
        detalhe: null,
      });
    } catch (err) {
      if (eh401(err)) throw new ErroAutenticacao();
      if (codigoDoErro(err) === "HASH_DIVERGENTE" && a.tentativas + 1 < MAX_TENTATIVAS_HASH_DIVERGENTE) {
        // O que chegou ao servidor nao tem o hash da captura: pode ser corrupcao no transito. Tenta de novo (o arquivo
        // continua na fila). Se persistir, cai no caso abaixo e fica REJEITADO com o motivo (nunca apagado).
        await atualizarArquivo(a.client_file_id, {
          codigo: "HASH_DIVERGENTE",
          detalhe: "O arquivo chegou diferente do original; nova tentativa no próximo ciclo.",
          somarTentativa: true,
        });
        falha = "Arquivo corrompido no envio; tentando novamente.";
        continue;
      }
      if (erroDefinitivo(err)) {
        // 400/403/404/409/413/422: o servidor recusou o arquivo em si. Fica registrado (rejeitado),
        // o evento que o referencia mostra o motivo e a fila segue.
        await atualizarArquivo(a.client_file_id, {
          status: "rejeitado",
          codigo: codigoDoErro(err) ?? `HTTP_${isAxiosError(err) ? err.response?.status : "ERRO"}`,
          detalhe: getErrorMessage(err, "O servidor recusou o arquivo."),
          somarTentativa: true,
        });
      } else {
        await atualizarArquivo(a.client_file_id, { somarTentativa: true });
        falha = getErrorMessage(err, "Falha ao enviar arquivos.");
      }
    }
  }
  return falha;
}

// ---------------------------------------------------------------------------------------------
// Passo 2: eventos
// ---------------------------------------------------------------------------------------------
interface ResultadoServidor {
  client_event_id: string;
  resultado: "aplicado" | "duplicado" | "rejeitado";
  codigo: string | null;
  detalhe: string | null;
}

/**
 * Eventos prontos para envio, em ordem. Um evento cujo arquivo ainda NAO foi confirmado segura
 * ele e os seguintes da mesma visita (SY-08: arquivo antes do evento; evita sequencia fora de ordem).
 */
async function selecionarEnviaveis(pendentes: EventoOutbox[]): Promise<EventoOutbox[]> {
  const todasRefs = Array.from(new Set(pendentes.flatMap((e) => refsDoPayload(e.payload))));
  const arquivos = new Map((await obterArquivos(todasRefs)).map((a) => [a.client_file_id, a]));
  const visitasSegura = new Set<number>();
  const prontos: EventoOutbox[] = [];
  for (const ev of pendentes) {
    if (visitasSegura.has(ev.id_visita)) continue;
    const aguardando = refsDoPayload(ev.payload).some((r) => arquivos.get(r)?.status === "pendente");
    if (aguardando) {
      visitasSegura.add(ev.id_visita);
      continue;
    }
    prontos.push(ev);
  }
  return prontos;
}

async function tratarResultado(
  ev: EventoOutbox,
  r: ResultadoServidor,
  arquivos: Map<string, ArquivoOutbox>
): Promise<void> {
  const agora = Date.now();

  if (r.resultado === "rejeitado") {
    if (r.codigo === "ARQUIVO_AUSENTE") {
      // Transitorio (SY-08): nao foi gravado no servidor. Mantem pendente e reenvia o MESMO id.
      // Se o arquivo foi definitivamente recusado, nao ha como a acao ser aplicada: registra.
      const recusado = refsDoPayload(ev.payload)
        .map((ref) => arquivos.get(ref))
        .find((a) => a && a.status === "rejeitado");
      if (recusado) {
        await atualizarEvento(ev.client_event_id, {
          status: "rejeitado",
          codigo: "ARQUIVO_REJEITADO",
          detalhe: recusado.detalhe ?? "O servidor recusou a foto/assinatura desta ação.",
        });
      } else {
        await atualizarEvento(ev.client_event_id, {
          codigo: r.codigo,
          detalhe: r.detalhe,
          somarTentativa: true,
        });
      }
      return;
    }
    await atualizarEvento(ev.client_event_id, {
      status: "rejeitado",
      codigo: r.codigo ?? "REJEITADO",
      detalhe: r.detalhe,
      enviado_ms: agora,
    });
    return;
  }

  // aplicado | duplicado. Duplicado devolve codigo/detalhe do resultado anterior: com codigo,
  // o evento ja tinha sido rejeitado antes (resposta perdida).
  if (r.resultado === "duplicado" && r.codigo) {
    await atualizarEvento(ev.client_event_id, {
      status: "rejeitado",
      codigo: r.codigo,
      detalhe: r.detalhe,
      enviado_ms: agora,
    });
    return;
  }
  await atualizarEvento(ev.client_event_id, {
    status: "enviado",
    codigo: null,
    detalhe: null,
    enviado_ms: agora,
  });
}

function corpoDoEvento(ev: EventoOutbox) {
  return {
    client_event_id: ev.client_event_id,
    tipo: ev.tipo,
    id_os: ev.id_os,
    id_visita: ev.id_visita,
    ocorrido_em: ev.ocorrido_em,
    payload: ev.payload,
  };
}

async function postarLote(dispositivo: string, eventos: EventoOutbox[]): Promise<ResultadoServidor[]> {
  const res = await api.post<{ resultados: ResultadoServidor[] }>(
    "/sync/eventos",
    {
      dispositivo_id: dispositivo,
      enviado_em: agoraIso(),
      eventos: eventos.map(corpoDoEvento),
    },
    { semRedirecionarLogin: true }
  );
  return Array.isArray(res.data?.resultados) ? res.data.resultados : [];
}

async function enviarEventos(idTecnico: number): Promise<string | null> {
  const todos = await listarEventosPendentes(idTecnico);
  if (todos.length === 0) return null;
  const prontos = await selecionarEnviaveis(todos);
  if (prontos.length === 0) return null;

  const dispositivo = await dispositivoId();
  const refs = Array.from(new Set(prontos.flatMap((e) => refsDoPayload(e.payload))));
  const arquivos = new Map((await obterArquivos(refs)).map((a) => [a.client_file_id, a]));
  let falha: string | null = null;

  for (let i = 0; i < prontos.length; i += MAX_EVENTOS_POR_LOTE) {
    const lote = prontos.slice(i, i + MAX_EVENTOS_POR_LOTE);
    try {
      const resultados = await postarLote(dispositivo, lote);
      const porId = new Map(resultados.map((r) => [r.client_event_id, r]));
      for (const ev of lote) {
        const r = porId.get(ev.client_event_id);
        if (r) await tratarResultado(ev, r, arquivos);
        else await atualizarEvento(ev.client_event_id, { somarTentativa: true }); // sem resposta: continua pendente
      }
    } catch (err) {
      if (eh401(err)) throw new ErroAutenticacao();
      if (erroDefinitivo(err)) {
        // O lote inteiro foi recusado (ex.: 422 por um evento mal formado). Isola um a um para a
        // fila nao travar: so o evento problematico e rejeitado.
        falha = (await enviarUmAUm(dispositivo, lote, arquivos)) ?? falha;
      } else {
        for (const ev of lote) await atualizarEvento(ev.client_event_id, { somarTentativa: true });
        falha = getErrorMessage(err, "Falha ao enviar as ações.");
        break; // rede/servidor indisponivel: os proximos lotes teriam o mesmo destino
      }
    }
  }
  return falha;
}

async function enviarUmAUm(
  dispositivo: string,
  lote: EventoOutbox[],
  arquivos: Map<string, ArquivoOutbox>
): Promise<string | null> {
  let falha: string | null = null;
  for (const ev of lote) {
    try {
      const [r] = await postarLote(dispositivo, [ev]);
      if (r) await tratarResultado(ev, r, arquivos);
    } catch (err) {
      if (eh401(err)) throw new ErroAutenticacao();
      if (erroDefinitivo(err)) {
        await atualizarEvento(ev.client_event_id, {
          status: "rejeitado",
          codigo: "VALIDACAO",
          detalhe: getErrorMessage(err, "O servidor recusou os dados desta ação."),
          enviado_ms: Date.now(),
        });
      } else {
        await atualizarEvento(ev.client_event_id, { somarTentativa: true });
        falha = getErrorMessage(err, "Falha ao enviar as ações.");
        break;
      }
    }
  }
  return falha;
}

// ---------------------------------------------------------------------------------------------
// Passo 3: cache de OS
// ---------------------------------------------------------------------------------------------
async function atualizarCacheDeOS(idTecnico: number): Promise<void> {
  const inicio = Date.now();
  const res = await api.get<RespostaMinhasOs>("/sync/minhas-os", { semRedirecionarLogin: true });
  if (!res.data || !Array.isArray(res.data.os)) {
    throw new Error("Resposta inesperada de /sync/minhas-os.");
  }
  await substituirCache(idTecnico, res.data, inicio);
}

/** Libera do aparelho os arquivos ja confirmados e que nenhuma acao pendente/rejeitada usa mais. */
async function limparArquivosConfirmados(idTecnico: number): Promise<void> {
  const liberaveis = await listarArquivosLiberaveis(idTecnico);
  for (const a of liberaveis) {
    if (!a.caminho_local) continue;
    if (await arquivoEmUso(a.client_file_id)) continue;
    await removerArquivoLocal(a.caminho_local);
    await atualizarArquivo(a.client_file_id, { caminho_local: null });
  }
}

// ---------------------------------------------------------------------------------------------
// Orquestracao
// ---------------------------------------------------------------------------------------------
async function executar(): Promise<ResultadoSync> {
  const net = await NetInfo.fetch();
  const online = estaOnline(net);
  atualizarStatus({ online });
  if (!online) return { ok: false, motivo: "offline" };

  const av = await avaliarSessao();
  atualizarStatus({ situacaoSessao: av.situacao });
  if (av.situacao === "sem_sessao" || !av.sessao) return { ok: false, motivo: "sem_sessao" };
  if (av.situacao !== "ok") {
    // JWT expirado (ou janela de 24 h vencida): nada e enviado; a fila fica intacta.
    return { ok: false, motivo: "login_necessario", mensagem: "Entre novamente para enviar as ações salvas." };
  }

  const idTecnico = av.sessao.idTecnico;
  atualizarStatus({ sincronizando: true });
  try {
    const falhaArq = await enviarArquivos(idTecnico);
    const falhaEv = await enviarEventos(idTecnico);
    let falhaCache: string | null = null;
    try {
      await atualizarCacheDeOS(idTecnico);
    } catch (err) {
      if (eh401(err)) throw new ErroAutenticacao();
      falhaCache = getErrorMessage(err, "Falha ao atualizar as OS.");
    }
    await limparArquivosConfirmados(idTecnico);

    const falha = falhaArq ?? falhaEv ?? falhaCache;
    if (falha) {
      atualizarStatus({ erroSync: falha });
      return { ok: false, motivo: "erro", mensagem: falha };
    }
    atualizarStatus({ erroSync: null, ultimoSync: Date.now() });
    return { ok: true, motivo: "ok" };
  } catch (err) {
    if (err instanceof ErroAutenticacao) {
      await marcarJwtRejeitado(); // fila preservada; novo login online exigido
      return {
        ok: false,
        motivo: "login_necessario",
        mensagem: "Sessão expirada. Entre novamente para enviar as ações salvas.",
      };
    }
    const mensagem = getErrorMessage(err, "Falha na sincronização.");
    atualizarStatus({ erroSync: mensagem });
    return { ok: false, motivo: "erro", mensagem };
  } finally {
    atualizarStatus({ sincronizando: false });
    await atualizarContagens();
  }
}

/**
 * Sincroniza agora. Chamadas simultaneas se juntam: se chegar uma acao durante o envio, ha uma
 * segunda passada ao final. A espera crescente so vale para o agendador: acoes do tecnico e o
 * botao "Sincronizar agora" sempre tentam imediatamente.
 */
export function sincronizar(): Promise<ResultadoSync> {
  if (emAndamento) {
    repetir = true;
    return emAndamento;
  }
  emAndamento = (async () => {
    let resultado: ResultadoSync;
    do {
      repetir = false;
      resultado = await executar();
    } while (repetir && resultado.ok);

    if (resultado.ok) {
      falhasSeguidas = 0;
      proximaTentativaEm = 0;
    } else if (resultado.motivo === "erro") {
      falhasSeguidas += 1;
      proximaTentativaEm =
        Date.now() + Math.min(BACKOFF_MAXIMO_MS, BACKOFF_INICIAL_MS * 2 ** (falhasSeguidas - 1));
    }
    return resultado;
  })().finally(() => {
    emAndamento = null;
    agendar();
  });
  return emAndamento;
}

/** Dispara sem esperar (apos cada acao, ao abrir o app, ao voltar a conexao). */
export function dispararSync(): void {
  sincronizar().catch(() => undefined);
}

// ---------------------------------------------------------------------------------------------
// Agendador (intervalo + espera crescente)
// ---------------------------------------------------------------------------------------------
function agendar(): void {
  if (timer) clearTimeout(timer);
  const espera =
    falhasSeguidas > 0
      ? Math.max(1_000, proximaTentativaEm - Date.now())
      : INTERVALO_BASE_MS;
  timer = setTimeout(async () => {
    const s = getStatus();
    const ultimoCache = (await ultimaAtualizacaoCache()) ?? 0;
    const temFila = s.pendentes > 0 || s.arquivosPendentes > 0;
    const cacheVelho = Date.now() - ultimoCache > REFRESH_CACHE_MS;
    if (s.online && s.situacaoSessao === "ok" && (temFila || cacheVelho)) {
      dispararSync();
    } else {
      agendar();
    }
  }, espera);
}

let iniciado = false;

/** Liga conexao, retorno ao primeiro plano e intervalo. Chamar uma vez na raiz do app. */
export function iniciarSincronizacao(): () => void {
  if (iniciado) return () => undefined;
  iniciado = true;

  // "Online" = a PROPRIA API responde (GET / e publico, AR-03), nao apenas ha rede. Evita falso
  // "sem conexao" em redes que bloqueiam o servidor de teste padrao do Android.
  if (API_BASE_URL) {
    NetInfo.configure({
      reachabilityUrl: API_BASE_URL.replace(/\/api$/, "/"),
      reachabilityMethod: "GET",
      reachabilityTest: async (resposta) => resposta.status > 0 && resposta.status < 500,
      reachabilityLongTimeout: 60_000,
      reachabilityShortTimeout: 10_000,
      reachabilityRequestTimeout: 15_000,
    });
  }

  const removerNet = NetInfo.addEventListener((s) => {
    const online = estaOnline(s);
    const voltou = online && !getStatus().online;
    atualizarStatus({ online });
    if (voltou) {
      falhasSeguidas = 0; // conexao nova: tenta ja
      proximaTentativaEm = 0;
      dispararSync();
    }
  });

  const removerApp = AppState.addEventListener("change", (estado) => {
    if (estado === "active") {
      atualizarContagens().finally(() => dispararSync());
    }
  });

  atualizarContagens().finally(() => dispararSync()); // ao abrir o app
  agendar();

  return () => {
    removerNet();
    removerApp.remove();
    if (timer) clearTimeout(timer);
    iniciado = false;
  };
}
