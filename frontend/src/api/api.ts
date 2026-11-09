// src/api/api.ts
import axios from "axios";
import { getToken } from "@/utils/storage";
import { emitSessionExpired, marcarSessaoExpirada } from "@/utils/session";
import { marcarJwtRejeitado } from "@/offline/sessao";

declare module "axios" {
  interface AxiosRequestConfig {
    /** true = o chamador trata o 401 (nao emitir "sessao expirada" nem ir ao login). */
    semRedirecionarLogin?: boolean;
  }
}

/**
 * URL base da API (PR-14).
 *
 * Definida por EXPO_PUBLIC_API_URL (ver .env.example). Aceita com ou sem o sufixo "/api".
 * Fallback apenas em desenvolvimento (__DEV__): 10.0.2.2 e o alias do host no emulador
 * Android. Em build de producao sem a variavel a API fica "nao configurada" e as
 * chamadas falham com mensagem explicita (nunca aponta para um endereco de emulador).
 */
const EMULATOR_FALLBACK = "http://10.0.2.2:8000";

function resolverBaseUrl(): string {
  const configurada = (process.env.EXPO_PUBLIC_API_URL ?? "").trim();
  const bruta = configurada || (__DEV__ ? EMULATOR_FALLBACK : "");
  if (!bruta) return "";
  const semBarra = bruta.replace(/\/+$/, "");
  return semBarra.endsWith("/api") ? semBarra : `${semBarra}/api`;
}

export const API_BASE_URL = resolverBaseUrl();

/** Em build de producao a URL precisa ser HTTPS (token e dados trafegam nela). */
const HTTP_EM_PRODUCAO = !__DEV__ && /^http:\/\//i.test(API_BASE_URL);

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15000,
});

// request interceptor -- injeta o token e barra chamadas sem URL configurada
api.interceptors.request.use(
  async (config) => {
    if (HTTP_EM_PRODUCAO) {
      throw new Error(
        "EXPO_PUBLIC_API_URL usa http://. Em produção a API deve usar https://."
      );
    }

    if (!API_BASE_URL) {
      throw new Error(
        "URL da API não configurada. Defina EXPO_PUBLIC_API_URL e gere o app novamente."
      );
    }

    const token = await getToken();

    if (token) {
      config.headers = config.headers || {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// response interceptor -- 401 encerra a sessao (RN-39). Mensagens de erro ficam por
// conta de quem chama (alertError/getErrorMessage), para nao duplicar alertas.
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const status = error?.response?.status;
    const url = String(error?.config?.url ?? "");
    const ehLogin = url.includes("auth/login");

    // Sincronizacao em segundo plano trata o 401 sozinha (fila preservada + aviso de novo login);
    // nao deve arrancar o tecnico da tela em que esta.
    if (status === 401 && !ehLogin && !error?.config?.semRedirecionarLogin) {
      // Offline-first: o token NAO e apagado aqui. A sessao e marcada como rejeitada para que
      // nada seja enviado ate um novo login ONLINE; a fila e o cache de OS permanecem (RN-39).
      await marcarJwtRejeitado();
      marcarSessaoExpirada(error);
      emitSessionExpired();
    }
    return Promise.reject(error);
  }
);

// Garantir envio correto de JSON sem quebrar FormData
api.defaults.headers.post["Content-Type"] = "application/json";

// Não alterar automaticamente o corpo das requisições
api.defaults.transformRequest = [(data, headers) => {
  if (headers?.["Content-Type"] === "application/json") {
    return JSON.stringify(data);   // JSON
  }
  return data;                      // FormData ou outros
}];

export default api;
