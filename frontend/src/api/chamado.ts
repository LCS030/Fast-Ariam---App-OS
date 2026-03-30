// src/api/chamados.ts

import api from "./api";

// Tipagem opcional — coloquei somente tipos usados pelo frontend.
export interface Chamado {
  is_completed: any;
  id_os: number;
  cliente_nome: string;
  data_agendamento: string;
  descricao_cliente: string;
  status: string;
  visitas: any[];
}

// -------- LISTAR TODOS --------
export async function listarChamados(): Promise<Chamado[]> {
  const res = await api.get("/chamados");
  return res.data;
}

// -------- BUSCAR POR ID --------
export async function getChamadoPorId(id: number): Promise<Chamado> {
  const res = await api.get(`/chamados/${id}`);
  return res.data;
}

// -------- ATUALIZAR STATUS DO CHAMADO --------
export async function atualizarChamadoStatus(id: number, status: string) {
  const res = await api.patch(`/chamados/${id}`, { status });
  return res.data;
}

// -------- INICIAR ATENDIMENTO --------
export async function iniciarAtendimento(chamadoId: number, visitaId: any) {
  const res = await api.post(`/chamados/${chamadoId}/iniciar-atendimento`);
  return res.data;
}

export async function concluirChamado(chamadoId: number) {
  const res = await api.post(`/chamados/${chamadoId}/concluir`);
  return res.data;
}

// -------- UPLOAD DE FOTOS --------

/**
 * Upload de foto de defeito (antes do reparo)
 */
export async function uploadFotoDefeito(
  chamadoId: number,
  visitaId: number,
  servicoId: number,
  imageUri: string
): Promise<any> {
  const formData = new FormData();
  formData.append("tipo", "defeito");
  formData.append("file", {
    uri: imageUri,
    type: "image/jpeg",
    name: `foto_defeito_${Date.now()}.jpg`,
  } as any);

  const res = await api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}/upload-foto`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return res.data;
}

/**
 * Upload de foto de conserto (após o reparo)
 */
export async function uploadFotoConserto(
  chamadoId: number,
  visitaId: number,
  servicoId: number,
  imageUri: string
): Promise<any> {
  const formData = new FormData();
  formData.append("tipo", "conserto");
  formData.append("file", {
    uri: imageUri,
    type: "image/jpeg",
    name: `foto_conserto_${Date.now()}.jpg`,
  } as any);

  const res = await api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}/upload-foto`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
  return res.data;
}

/**
 * Busca todas as fotos de um serviço
 */
export async function getPhotosServico(
  chamadoId: number,
  visitaId: number,
  servicoId: number
): Promise<any> {
  const res = await api.get(
    `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}/fotos`
  );
  return res.data;
}