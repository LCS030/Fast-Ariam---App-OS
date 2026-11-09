// src/api/chamado.ts
import api from "./api";
import { anexarImagem, ArquivoImagem, UPLOAD_TIMEOUT_MS } from "./arquivo";

// Status oficiais (SDD secao 5). "Cancelado" nao e status: use is_cancelled.
export type StatusOS =
  | "Pendente"
  | "Agendado"
  | "Em Atendimento"
  | "Pausado"
  | "Aguardando Reagendamento"
  | "Finalizado";

/**
 * Equipamento vinculado a OS pelo administrador (SDD 6.13). SOMENTE LEITURA no app:
 * o tecnico nao cadastra nem edita modelo ou numero de serie (RN-42).
 */
export interface OsEquipamento {
  id_os_equipamento: number;
  id_equipamento_modelo?: number;
  modelo: string;
  numero_serie: string;
}

/**
 * Registro de servico de um equipamento na visita (SDD 6.7.1). Criado pelo servidor;
 * o tecnico apenas o preenche (defeitos, materiais, conserto).
 */
export interface ServicoEquipamento {
  id_servico: number;
  id_os_equipamento?: number | null;
  /** Somente leitura, vindos do vinculo da OS. */
  modelo?: string | null;
  numero_serie?: string | null;
  /** Marca de "conserto salvo" (POST .../salvar-conserto); null = ainda nao salvo. */
  conserto_salvo_em?: string | null;
  is_legado?: boolean;
  /** Somente na resposta de servicos legados (is_legado = true); nunca enviados. */
  numero_serie_atendido?: string | null;
  nome_equipamento?: string | null;
  defeitos_principais?: string[];
  sub_defeitos_refrigeracao?: string[];
  sub_defeitos_compressor?: string[];
  sub_defeitos_vazamento?: string[];
  sub_defeitos_outros?: string[];
  sub_defeitos_iluminacao?: string[];
  sub_defeitos_estrutura?: string[];
  defeito_outros_descricao?: string | null;
  vazamento_ponto_descricao?: string | null;
  materiais_utilizados?: { nome: string; quantidade: number; valor: number }[];
}

export interface Visita {
  id_visita: number;
  id_os?: number;
  data_visita?: string | null;
  km_inicio_ida?: number | null;
  km_fim_ida?: number | null;
  km_inicio_volta?: number | null;
  km_fim_volta?: number | null;
  valor_pedagio?: number | null;
  valor_frete_devolucao?: number | null;
  servico_finalizado?: boolean;
  comprovante_pedagio_urls?: string[];
  comprovante_frete_urls?: string[];
  servicos_realizados?: ServicoEquipamento[];
}

export interface Chamado {
  id_os: number;
  id_cliente?: number;
  cliente_nome?: string | null;
  pedido?: string | null;
  descricao_cliente?: string | null;
  data_agendamento?: string | null;
  // string: o servidor pode devolver valores legados (ex.: "Aberto") que o app apenas exibe.
  status: StatusOS | string;
  is_cancelled?: boolean;
  /** Equipamentos da OS (modelo + serie), somente leitura. */
  equipamentos?: OsEquipamento[];
  visitas?: Visita[];
}

export interface FotoServico {
  id_foto: number;
  id_servico: number;
  tipo: "defeito" | "conserto";
  url: string;
}

// -------- LISTAR (somente as OS do tecnico autenticado; filtro e do servidor) --------
export async function listarChamados(): Promise<Chamado[]> {
  const res = await api.get<Chamado[]>("/chamados/");
  return res.data;
}

// -------- BUSCAR POR ID --------
export async function getChamadoPorId(id: number): Promise<Chamado> {
  const res = await api.get<Chamado>(`/chamados/${id}`);
  return res.data;
}

// -------- UPLOAD DE FOTOS DE SERVICO --------
/**
 * Defeito: sem resolucao minima. Conserto: minimo 960x1280 (validado no app na captura e no servidor).
 */
export async function uploadFotoServico(
  chamadoId: number,
  visitaId: number,
  servicoId: number,
  tipo: "defeito" | "conserto",
  arquivo: ArquivoImagem
) {
  const formData = new FormData();
  formData.append("tipo", tipo);
  anexarImagem(formData, "file", arquivo, `foto_${tipo}`);

  const res = await api.post(
    `/chamados/${chamadoId}/visitas/${visitaId}/servicos/${servicoId}/upload-foto`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: UPLOAD_TIMEOUT_MS,
    }
  );
  return res.data;
}
