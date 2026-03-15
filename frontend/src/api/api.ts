// src/api/api.ts
import axios from "axios";
import { getToken, removeToken } from "@/utils/storage";
import { alertError } from "@/utils/alerts";

const api = axios.create({
  baseURL: " http://10.0.2.2:8000/api",
  timeout: 15000,
});


// request interceptor -- inject token
api.interceptors.request.use(
  async (config) => {
    const token = await getToken();

    if (token) {
      // RN não usa AxiosHeaders, mas o Axios converte internamente
      config.headers = config.headers || {};
      (config.headers as any).Authorization = `Bearer ${token}`;
    }

    return config;
  },
  (error) => Promise.reject(error)
);

// response interceptor
api.interceptors.response.use(
  (res) => res,
  async (error) => {
    const status = error.response?.status;
    if (status === 401) {
      // remove token and advise re-login
      await removeToken();
      alertError(null, "Sessão expirada. Faça login novamente.");
    } else if (status === 403) {
      alertError(null, "Acesso negado.");
    } else if (status >= 500) {
      alertError(null, "Erro no servidor. Tente novamente.");
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
