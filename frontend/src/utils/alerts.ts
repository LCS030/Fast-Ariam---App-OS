// src/utils/alerts.ts
import { Alert } from "react-native";
import { isAxiosError } from "axios";
import { isSessaoExpirada } from "@/utils/session";

export function alertInfo(title: string, message?: string) {
  Alert.alert(title, message ?? "");
}

function formatarDetail(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;

  // 422 do FastAPI: lista de { loc, msg, type }
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d: any) =>
        typeof d?.msg === "string" ? d.msg.replace(/^Value error, /, "") : null
      )
      .filter((m): m is string => !!m);
    return msgs.length ? msgs.join("\n") : null;
  }

  return null;
}

/**
 * Converte qualquer erro em uma mensagem legivel para o tecnico.
 * Erro de rede e erro do servidor sao distintos de "lista vazia" ou dado ausente.
 */
export function getErrorMessage(
  err: unknown,
  fallbackMessage = "Ocorreu um erro inesperado."
): string {
  if (isAxiosError(err)) {
    if (!err.response) {
      if (err.code === "ECONNABORTED") {
        return "O servidor demorou para responder. Verifique a conexão e tente novamente.";
      }
      return "Sem conexão com o servidor. Verifique a internet e tente novamente.";
    }

    const data = err.response.data as { detail?: unknown; message?: unknown } | undefined;
    const doServidor = formatarDetail(data?.detail ?? data?.message);
    if (doServidor) return doServidor;

    const status = err.response.status;
    if (status === 401) return "Sessão expirada. Faça login novamente.";
    if (status === 403) return "Acesso negado.";
    if (status === 413) return "Arquivo muito grande. O limite por imagem é de 15 MB.";
    if (status >= 500) return "Erro no servidor. Tente novamente em instantes.";
    return fallbackMessage;
  }

  if (err instanceof Error && err.message) return err.message;
  return fallbackMessage;
}

export function alertError(error: unknown, fallbackMessage = "Ocorreu um erro inesperado.") {
  // Sessao expirada: o aviso e a navegacao para o login sao feitos pela raiz do app.
  if (isSessaoExpirada(error)) return;
  Alert.alert("Erro", getErrorMessage(error, fallbackMessage));
}

/** 409: pendencia/regra de fase do servidor (ex.: falta foto). O detail e exibido ao tecnico. */
export function isConflito(err: unknown): boolean {
  return isAxiosError(err) && err.response?.status === 409;
}
