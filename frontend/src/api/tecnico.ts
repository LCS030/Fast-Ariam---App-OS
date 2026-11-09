// src/api/tecnico.ts
import api from "./api";
import qs from "qs";

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

// Payload de GET /api/auth/me (SDD 6.2, PR-06)
export interface Perfil {
  id_tecnico: number;
  nome: string;
  email: string;
  role: "admin" | "tecnico";
  is_active: boolean;
}

export async function loginTecnico(email: string, senha: string) {
  const data = qs.stringify({
    username: email.trim().toLowerCase(),
    password: senha,
  });

  const res = await api.post<LoginResponse>("/auth/login", data, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });

  return res.data;
}

export async function getPerfilTecnico(): Promise<Perfil> {
  const res = await api.get<Perfil>("/auth/me");
  return res.data;
}
