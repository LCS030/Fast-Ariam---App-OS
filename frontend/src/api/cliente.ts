// src/api/cliente.ts
import api from "./api";

export interface Cliente {
  id_cliente: number;
  razao_social: string;
  telefone?: string | null;
  endereco?: string | null;
  numero?: string | null;
  bairro?: string | null;
  cidade?: string | null;
  uf?: string | null;
}

// Tecnico so le clientes das proprias OS (SDD 6.4 / SEG-11).
export async function getClientePorId(id: number): Promise<Cliente> {
  // Dado acessorio: um 401 aqui nao deve tirar o tecnico da tela (a fila trata a sessao).
  const res = await api.get<Cliente>(`/clientes/${id}`, { semRedirecionarLogin: true });
  return res.data;
}
