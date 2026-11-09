// Sessao offline (RN-39, RNF-10, AR-08, SEG-13).
// - Primeiro login exige internet; o token fica no SecureStore (utils/storage.ts).
// - Guardamos aqui o instante do ultimo login ONLINE e o tecnico dono da sessao.
// - Offline vale por ate 24 h desde esse login. Nao existe refresh token.
// - JWT expirado: a fila continua intacta e novas acoes locais seguem permitidas ate o limite de
//   24 h, mas NADA e enviado ate um novo login online.
// - Passadas 24 h: novas operacoes sao bloqueadas. Em nenhum caso a outbox e apagada.
import * as SecureStore from "expo-secure-store";
import { getToken } from "@/utils/storage";
import { ErroOffline } from "./tipos";

const CHAVE_SESSAO = "fast_ariam_sessao_offline";

/** Janela de operacao offline desde o ultimo login online (RN-39). */
export const LIMITE_OFFLINE_MS = 24 * 60 * 60 * 1000;

export interface SessaoLocal {
  /** Instante (ms) do ultimo login online bem-sucedido. */
  loginEm: number;
  idTecnico: number;
  nome: string;
  /** O servidor respondeu 401 a um envio: exige novo login online antes de sincronizar. */
  jwtRejeitado: boolean;
}

export type SituacaoSessao =
  | "sem_sessao" // sem token/sessao: login online necessario
  | "ok"
  | "jwt_expirado" // fila preservada; novo login online necessario para sincronizar
  | "offline_expirada"; // passou de 24 h desde o login: sem novas operacoes

let cache: SessaoLocal | null | undefined; // undefined = ainda nao lida

async function ler(): Promise<SessaoLocal | null> {
  if (cache !== undefined) return cache;
  try {
    const bruto = await SecureStore.getItemAsync(CHAVE_SESSAO);
    cache = bruto ? (JSON.parse(bruto) as SessaoLocal) : null;
  } catch {
    cache = null;
  }
  return cache;
}

async function gravar(s: SessaoLocal): Promise<void> {
  cache = s;
  await SecureStore.setItemAsync(CHAVE_SESSAO, JSON.stringify(s));
}

/** Chamada logo apos um login online confirmado (token ja gravado e perfil validado). */
export async function iniciarSessaoOnline(perfil: { id_tecnico: number; nome: string }) {
  await gravar({
    loginEm: Date.now(),
    idTecnico: perfil.id_tecnico,
    nome: perfil.nome,
    jwtRejeitado: false,
  });
}

/** Logout: apaga so a sessao. A outbox e o cache de OS permanecem (RN-39). */
export async function encerrarSessao(): Promise<void> {
  cache = null;
  try {
    await SecureStore.deleteItemAsync(CHAVE_SESSAO);
  } catch {
    // sem sessao armazenada
  }
}

export async function marcarJwtRejeitado(): Promise<void> {
  const s = await ler();
  if (s && !s.jwtRejeitado) await gravar({ ...s, jwtRejeitado: true });
}

export async function getSessao(): Promise<SessaoLocal | null> {
  return ler();
}

/** Decodifica o `exp` (segundos) do JWT sem validar assinatura (so para saber se expirou). */
export function expiracaoDoJwt(token: string): number | null {
  try {
    const parte = token.split(".")[1];
    if (!parte) return null;
    const b64 = parte.replace(/-/g, "+").replace(/_/g, "/");
    const preenchido = b64 + "=".repeat((4 - (b64.length % 4)) % 4);
    if (typeof atob !== "function") return null; // Hermes (RN 0.81) disponibiliza atob
    const json = atob(preenchido);
    const exp = JSON.parse(json).exp;
    return typeof exp === "number" ? exp : null;
  } catch {
    return null;
  }
}

export interface AvaliacaoSessao {
  situacao: SituacaoSessao;
  sessao: SessaoLocal | null;
  token: string | null;
}

export async function avaliarSessao(agora: number = Date.now()): Promise<AvaliacaoSessao> {
  const [token, sessao] = await Promise.all([getToken(), ler()]);
  if (!token || !sessao) return { situacao: "sem_sessao", sessao, token };

  if (agora - sessao.loginEm > LIMITE_OFFLINE_MS) {
    return { situacao: "offline_expirada", sessao, token };
  }
  const exp = expiracaoDoJwt(token);
  if (sessao.jwtRejeitado || (exp !== null && exp * 1000 <= agora)) {
    return { situacao: "jwt_expirado", sessao, token };
  }
  return { situacao: "ok", sessao, token };
}

export const MSG_SESSAO: Record<SituacaoSessao, string> = {
  sem_sessao: "Faça login com internet para usar o aplicativo.",
  ok: "",
  jwt_expirado:
    "Sua sessão expirou. As ações salvas continuam no aparelho; conecte-se e entre novamente para enviá-las.",
  offline_expirada:
    "Passaram-se mais de 24 horas desde o último login com internet. Conecte-se e entre novamente para continuar. " +
    "Nenhuma ação salva foi perdida.",
};

/**
 * Garante que novas acoes autenticadas podem ser registradas: precisa de sessao e dentro das 24 h.
 * JWT expirado NAO bloqueia o registro local (a fila espera o novo login).
 */
export async function exigirSessaoOperante(): Promise<SessaoLocal> {
  const { situacao, sessao } = await avaliarSessao();
  if (situacao === "sem_sessao" || situacao === "offline_expirada" || !sessao) {
    throw new ErroOffline("SESSAO_" + situacao.toUpperCase(), MSG_SESSAO[situacao]);
  }
  return sessao;
}
