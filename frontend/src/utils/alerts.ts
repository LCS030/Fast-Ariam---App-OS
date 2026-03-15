// File: src/utils/alerts.ts
// Path: src/utils/alerts.ts

import { Alert } from "react-native";
import { AxiosError } from "axios";

export function alertInfo(title: string, message?: string) {
  Alert.alert(title, message ?? "");
}

export function alertError(error: any, fallbackMessage = "Ocorreu um erro inesperado.") {
  console.log("❌ API ERROR:", error);

  if (error instanceof AxiosError) {
    const detail =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      fallbackMessage;

    Alert.alert("Erro", String(detail));
    return;
  }

  Alert.alert("Erro", fallbackMessage);
}

/**
 * Cria um alert de confirmação usando Promise.
 * await confirm("Deseja realmente excluir?");
 */
export function confirm(message: string, title = "Confirmar"): Promise<boolean> {
  return new Promise((resolve) => {
    Alert.alert(
      title,
      message,
      [
        { text: "Cancelar", style: "cancel", onPress: () => resolve(false) },
        { text: "OK", onPress: () => resolve(true) },
      ],
      { cancelable: true }
    );
  });
}

export function formatError(err: any): string {
  const detail = err?.response?.data?.detail;

  if (!detail) return "Erro desconhecido.";

  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail.map((d: any) =>
      d?.msg ? `${d.msg}` : JSON.stringify(d)
    ).join("\n");
  }

  return JSON.stringify(detail);
}