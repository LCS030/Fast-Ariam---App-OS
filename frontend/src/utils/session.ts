// Canal simples para avisar a raiz do app que a sessão expirou (HTTP 401).
// Evita ciclo de importação entre api.ts e o roteador.

type Listener = () => void;

const listeners = new Set<Listener>();
let jaNotificada = false;

export function onSessionExpired(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Dispara os listeners uma única vez por sessão (várias chamadas simultâneas podem receber 401). */
export function emitSessionExpired(): void {
  if (jaNotificada) return;
  jaNotificada = true;
  listeners.forEach((l) => l());
}

/** Deve ser chamada após um login bem-sucedido. */
export function resetSessionExpired(): void {
  jaNotificada = false;
}

const MARCA = "__sessaoExpirada";

export function marcarSessaoExpirada(err: unknown): void {
  if (err && typeof err === "object") {
    (err as Record<string, unknown>)[MARCA] = true;
  }
}

export function isSessaoExpirada(err: unknown): boolean {
  return !!err && typeof err === "object" && (err as Record<string, unknown>)[MARCA] === true;
}
