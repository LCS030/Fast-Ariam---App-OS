/**
 * Tipos do painel administrativo — alinhados ao contrato da API (SDD v0.3, seção 6).
 * Qualquer campo marcado como opcional pode não ser devolvido pela API na versão atual.
 */

export type UserRole = 'admin' | 'tecnico';

/** Valores EXATOS do enum de status da OS na API. "Cancelado" NÃO é status (ver is_cancelled). */
export const STATUS_OS = [
  'Pendente',
  'Agendado',
  'Em Atendimento',
  'Pausado',
  'Aguardando Reagendamento',
  'Finalizado',
] as const;

export type StatusChamado = (typeof STATUS_OS)[number];

/** Lista oficial de motivos de pausa (RN-29 / PR-15). "Outro" exige descrição. */
export const MOTIVOS_PAUSA = [
  'Peça pendente',
  'Cliente ausente',
  'Condições inseguras',
  'Aguardando aprovação',
  'Outro',
] as const;

export type MotivoPausa = (typeof MOTIVOS_PAUSA)[number];

export interface DadosBancarios {
  banco?: string;
  agencia?: string;
  conta?: string;
  pix?: string;
}

export interface Tecnico {
  id_tecnico: number;
  nome: string;
  email: string;
  cpf: string;
  cnpj?: string;
  inscricao_estadual?: string;
  telefone?: string;
  role?: UserRole;
  is_active?: boolean;
  dados_bancarios?: DadosBancarios | null;
}

export interface Cliente {
  id_cliente: number;
  razao_social: string;
  codigo?: number;
  contato_principal_nome?: string | null;
  contato_principal_telefone?: string | null;
  telefone: string;
  endereco: string;
  numero: string;
  bairro: string;
  cidade: string;
  uf: string;
  is_active?: boolean;
}

export interface MaterialUtilizado {
  id_material?: number;
  nome: string;
  quantidade: number;
  valor: number;
}

/** Modelo do catálogo de equipamentos (SDD 6.13). Só o nome; desativação lógica. */
export interface EquipamentoModelo {
  id_equipamento_modelo: number;
  modelo: string;
  is_active: boolean;
}

/** Equipamento vinculado à OS: modelo do catálogo + número de série (SDD 6.13). */
export interface OsEquipamento {
  id_os_equipamento: number;
  id_equipamento_modelo: number;
  modelo: string;
  numero_serie: string;
}

/** Foto de serviço com id (GET .../servicos/{s}/fotos), necessária para a correção administrativa (RN-49). */
export interface FotoServico {
  id_foto: number;
  id_servico: number;
  tipo: 'defeito' | 'conserto' | string;
  url: string;
}

export interface ServicoEquipamento {
  id_servico?: number;
  id_visita?: number;
  /** v0.5: vínculo com o equipamento da OS; modelo e série são somente leitura. */
  id_os_equipamento?: number | null;
  modelo?: string | null;
  numero_serie?: string | null;
  /** Marca de "conserto salvo" pelo técnico (RN-47); null = ainda não salvo. */
  conserto_salvo_em?: string | null;
  /** True em serviços anteriores à v0.5 (sem vínculo com a OS). */
  is_legado?: boolean;
  /** LEGADO: só preenchidos em serviços com is_legado = true. */
  numero_serie_atendido?: string | null;
  nome_equipamento?: string | null;
  defeitos_principais?: string[];
  defeito_outros_descricao?: string | null;
  sub_defeitos_refrigeracao?: string[];
  sub_defeitos_compressor?: string[];
  sub_defeitos_vazamento?: string[];
  vazamento_ponto_descricao?: string | null;
  sub_defeitos_outros?: string[];
  sub_defeitos_iluminacao?: string[];
  sub_defeitos_estrutura?: string[];
  materiais_utilizados?: MaterialUtilizado[];
  /** URLs devolvidas pela API (hoje relativas a /static; pendência: URL assinada, SEG-09). */
  fotos_defeito?: string[];
  fotos_conserto?: string[];
}

/** Registro de pausa devolvido em `visita.pausas[]` (SDD 4.6/4.7). Opcional para tolerar respostas antigas. */
export interface RegistroPausa {
  id_pausa: number;
  visita_id?: number;
  motivo: string;
  descricao?: string | null;
  criado_em?: string | null;
  encerrada_em?: string | null;
  is_ativa?: boolean;
  por_usuario_id?: number | null;
  por_papel?: 'admin' | 'tecnico' | string | null;
}

export interface Visita {
  id_visita: number;
  id_os: number;
  data_visita: string;

  // Deslocamento de ida
  km_inicio_ida?: number | null;
  km_fim_ida?: number | null;
  hora_inicio_ida?: string | null;
  hora_fim_ida?: string | null;
  ida_inicio_em?: string | null;
  ida_fim_em?: string | null;
  foto_inicio_ida_url?: string | null;
  foto_fim_ida_url?: string | null;

  // Atendimento
  hora_chegada_cliente?: string | null;
  hora_inicio_atendimento?: string | null;
  hora_fim_atendimento?: string | null;
  atendimento_inicio_em?: string | null;
  atendimento_fim_em?: string | null;
  descricao_servico_executado?: string | null;
  servico_finalizado?: boolean;
  pendencia?: string | null;

  // Deslocamento de volta
  km_inicio_volta?: number | null;
  km_fim_volta?: number | null;
  hora_inicio_volta?: string | null;
  hora_fim_volta?: string | null;
  volta_inicio_em?: string | null;
  volta_fim_em?: string | null;
  foto_inicio_volta_url?: string | null;
  foto_fim_volta_url?: string | null;

  km_total?: number | null;
  valor_pedagio?: number | null;
  valor_frete_devolucao?: number | null;

  odometro_inicio_url?: string | null;
  odometro_fim_url?: string | null;
  comprovante_pedagio_urls?: string[];
  comprovante_frete_urls?: string[];

  // Assinatura pertence à visita (RN-22 / PR-35)
  assinatura_url?: string | null;
  nome_cliente_assinatura?: string | null;
  documento_cliente?: string | null;

  pausas?: RegistroPausa[];
  servicos_realizados?: ServicoEquipamento[];
}

export interface EstadoVisitaResponse {
  pode_iniciar_deslocamento_ida: boolean;
  pode_finalizar_deslocamento_ida: boolean;
  pode_iniciar_atendimento: boolean;
  pode_finalizar_atendimento: boolean;
  pode_iniciar_deslocamento_volta: boolean;
  pode_finalizar_deslocamento_volta: boolean;
  pode_concluir_chamado?: boolean;
  pode_pausar_os: boolean;
  is_os_pausada: boolean;
  motivo_pausa?: string | null;
}

export interface CustoMaterialDetalhado {
  nome: string;
  quantidade: number;
  valor_unitario: number;
  valor_total: number;
}

export interface CustoVisitaDetalhado {
  id_visita: number;
  data: string;
  custo_total_materiais: number;
  custo_km: number;
  custo_pedagio: number;
  custo_frete: number;
  custo_tempo_servico: number;
  custo_tempo_deslocamento: number;
  subtotal_visita: number;
}

export interface CustoTotalResponse {
  id_os: number;
  custo_total_materiais: number;
  custo_total_km: number;
  custo_total_pedagio: number;
  custo_total_frete: number;
  custo_total_servico: number;
  custo_total_deslocamento: number;
  total_geral: number;
  detalhes_por_visita: CustoVisitaDetalhado[];
  detalhes_materiais_compilado: CustoMaterialDetalhado[];
  /** True quando vem do snapshot imutável de OS Finalizada (SDD 6.11). */
  congelado?: boolean;
  calculado_em?: string | null;
}

export interface OrdemServico {
  id_os: number;
  /**
   * Código amigável OS-AAAA-NNNN, DERIVADO NO FRONT a partir de data_abertura + id_os (PR-16).
   * Pendência: a API deve fornecer/persistir o identificador; ver utils/os.ts.
   */
  codigo_os: string;
  id_cliente: number;
  cliente: Cliente;
  cliente_nome?: string;
  id_tecnico_atribuido: number | null;
  tecnico?: Tecnico;
  status: StatusChamado;
  /** Cancelamento é flag lógica, não status (RN-12). */
  is_cancelled: boolean;
  motivo_cancelamento?: string | null;
  cancelado_em?: string | null;
  cancelado_por?: number | null;
  data_abertura: string;
  data_agendamento?: string | null;
  data_conclusao?: string | null;
  descricao_cliente: string;
  pedido?: string | null;
  em_garantia: boolean;
  /** v0.5: equipamentos da OS (mín. 1; OS legada pode vir vazia até o vínculo pelo admin). */
  equipamentos: OsEquipamento[];
  visitas: Visita[];
}

/** Usuário da sessão: claims do JWT, com o nome atualizado por GET /api/auth/me quando a API responde (PR-06). */
export interface UsuarioSessao {
  id_tecnico: number;
  email: string;
  nome: string;
  role: UserRole;
}
