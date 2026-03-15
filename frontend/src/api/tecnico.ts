// src/api/tecnicos.ts
import api from "./api";
import qs from "qs";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export async function loginTecnico(email: string, senha: string) {
  const data = qs.stringify({
    username: email.toLowerCase(),
    password: senha,
  });

  const res = await api.post<LoginResponse>("/auth/login", data, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });

  return res.data;
}

export async function getPerfilTecnico() {
  const res = await api.get("/auth/me");
  return res.data;
}
