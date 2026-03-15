
import api from "@/api/api"; 

export async function listarServicos(chamadoId: number, visitaId: number) {
  const res = await api.get(`/chamados/${chamadoId}/visitas/${visitaId}/servicos`);
  return res.data;
}

export async function criarServico(chamadoId: number, visitaId: number, body: any) {
  const res = await api.post(`/chamados/${chamadoId}/visitas/${visitaId}/servicos`, body);
  return res.data;
}

export async function atualizarServico(chamadoId: number, visitaId: number, servicoId: any, body: { numero_serie_atendido: any; nome_equipamento: any; defeitos_principais: never[]; sub_defeitos_compressor: string[]; sub_defeitos_vazamento: string[]; sub_defeitos_outros: string[]; sub_defeitos_iluminacao: string[]; sub_defeitos_estrutura: string[]; defeito_outros_descricao: string | null; vazamento_ponto_descricao: string | null; materiais_utilizados: { nome: string; quantidade: number; valor: number; }[]; }) {
  console.log(">>> AXIOS REQUEST:", {
    url: `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}`,
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    data: body,
  });

  return api.patch(
    `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}`,
    body,
    { headers: { "Content-Type": "application/json" } }
  );
}
