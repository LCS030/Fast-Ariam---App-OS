import { getToken } from "@/utils/storage";
import  api  from "./api";

// ===============================
// 1) INICIAR DESLOCAMENTO (IDA / VOLTA)
// ===============================
export async function iniciarDeslocamento(
  chamadoId: number,
  visitaId: number,
  data: { tipo: "ida" | "volta"; km_inicio: number }
) {
  const res = await api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/iniciar-deslocamento`,
    data,           // <-- corpo JSON correto
    {
      headers: { "Content-Type": "application/json" }
    }
  );

  return res.data;
}
// ===============================
// 2) UPLOAD DO HODÔMETRO (IDA / VOLTA)
// ===============================
export async function uploadDeslocamento(
  chamadoId: number,
  visitaId: number,
  uri: string,
  mimeType: string,
  tipo: "ida" | "volta",
  momento: "inicio" | "fim"
) {
  const filename = uri.split("/").pop() || "foto.jpg";

  const formData = new FormData();
  formData.append("file", {
    uri,
    name: filename,
    type: mimeType,
  } as any);

  formData.append("tipo", tipo);
  formData.append("momento", momento);

  return api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/upload-deslocamento`,
    formData,
    {
      headers: {
        "Content-Type": "multipart/form-data",
      },
    }
  );
}

export async function finalizarDeslocamento(
  chamadoId: number,
  visitaId: number,
  tipo: "ida" | "volta",
  kmFim: number
) {
  return api.post(`/chamados/${chamadoId}/visitas/${visitaId}/finalizar-deslocamento`, {
    tipo,
    km_fim: kmFim,
  });
}

export async function getEstadoVisita(chamadoId: number, visitaId: number) {
  const res = await api.get(`/chamados/${chamadoId}/visitas/${visitaId}/estado`);
  return res.data;
}

export async function iniciarAtendimento(chamadoId: number, visitaId: number) {
  const token = await getToken();
  return api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/iniciar-atendimento`,
    {},
    { headers: { Authorization: `Bearer ${token}` } }
  );
}

export async function iniciarAtendimentoVisita(chamadoId: number, visitaId: number) {
  const res = await api.post(`/chamados/${chamadoId}/visitas/${visitaId}/iniciar-atendimento`, {});
  return res.data;
}

export async function updateVisita(chamadoId: number, visitaId: number, body: any) {
  const res = await api.patch(`/chamados/${chamadoId}/visitas/${visitaId}`, body);
  return res.data;
}

export async function enviarAssinatura(chamadoId: number, visitaId: number, signatureBase64: string, nome: string, documento: string) {
  const payload = {
    assinatura_base64: signatureBase64,
    nome_cliente: nome,
    documento_cliente: documento
  };

  const res = await api.post(`/chamados/${chamadoId}/visitas/${visitaId}/finalizar-atendimento`, payload);
  return res.data;
}


