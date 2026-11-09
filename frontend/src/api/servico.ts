import api from "@/api/api";
import type { ServicoEquipamento } from "@/api/chamado";
import { agoraIso } from "@/api/visitas";

/**
 * Corpo do PATCH do tecnico (SDD 6.7.1, v0.5): somente defeitos, descricoes e materiais.
 * Modelo, numero de serie e nome do equipamento NAO existem aqui (o servidor responde 422).
 */
export interface ServicoPatch {
  defeitos_principais: string[];
  sub_defeitos_refrigeracao: string[];
  sub_defeitos_compressor: string[];
  sub_defeitos_vazamento: string[];
  sub_defeitos_outros: string[];
  sub_defeitos_iluminacao: string[];
  sub_defeitos_estrutura: string[];
  defeito_outros_descricao: string | null;
  vazamento_ponto_descricao: string | null;
  materiais_utilizados: { nome: string; quantidade: number; valor: number }[];
}

const base = (chamadoId: number, visitaId: number) =>
  `/chamados/${chamadoId}/visitas/${visitaId}/servicos`;

/** Um registro por equipamento da OS, criado pelo servidor (POST .../servicos responde 410). */
export async function listarServicos(chamadoId: number, visitaId: number) {
  const res = await api.get<ServicoEquipamento[]>(base(chamadoId, visitaId));
  return res.data;
}

export async function atualizarServico(
  chamadoId: number,
  visitaId: number,
  servicoId: number,
  body: ServicoPatch
) {
  const res = await api.patch<ServicoEquipamento>(
    `${base(chamadoId, visitaId)}/${servicoId}`,
    body
  );
  return res.data;
}

/** Marca o conserto como salvo (exige >= 1 defeito principal; idempotente). */
export async function salvarConserto(
  chamadoId: number,
  visitaId: number,
  servicoId: number,
  ocorridoEm: string = agoraIso()
) {
  const res = await api.post<ServicoEquipamento>(
    `${base(chamadoId, visitaId)}/${servicoId}/salvar-conserto`,
    { ocorrido_em: ocorridoEm }
  );
  return res.data;
}
