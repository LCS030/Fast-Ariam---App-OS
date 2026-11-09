/**
 * Camada de serviço do painel administrativo.
 * Regras de negócio e autorização pertencem à API (AR-02): aqui só se monta a requisição,
 * se normaliza a resposta e se propaga o erro. NUNCA há dados de fallback: em falha, o erro sobe
 * para a tela, que exibe mensagem clara e lista vazia (CA-05 / T-09).
 */
import {
  Cliente,
  CustoTotalResponse,
  EquipamentoModelo,
  EstadoVisitaResponse,
  FotoServico,
  MaterialUtilizado,
  OrdemServico,
  OsEquipamento,
  StatusChamado,
  Tecnico,
  UsuarioSessao,
} from '../types';
import { apiClient, ChamadoCreatePayload, OsEquipamentoPayload, TecnicoPayload } from './apiClient';
import { montarCodigoOS } from '../utils/os';

function nomeAPartirDoEmail(email: string): string {
  const local = email.includes('@') ? email.split('@')[0] : email;
  return local.replace(/[._-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) || email;
}

function normalizarChamado(item: any, clientes: Cliente[], tecnicos: Tecnico[]): OrdemServico {
  const id_os = Number(item.id_os);
  const id_cliente = Number(item.id_cliente);
  const cliente: Cliente =
    clientes.find((c) => Number(c.id_cliente) === id_cliente) ||
    ({
      id_cliente,
      razao_social: item.cliente_nome || `Cliente #${id_cliente}`,
      telefone: '',
      endereco: '',
      numero: '',
      bairro: '',
      cidade: '',
      uf: '',
    } as Cliente);

  const id_tecnico =
    item.id_tecnico_atribuido !== null && item.id_tecnico_atribuido !== undefined
      ? Number(item.id_tecnico_atribuido)
      : null;

  return {
    id_os,
    codigo_os: montarCodigoOS(id_os, item.data_abertura, item.codigo_os),
    id_cliente,
    cliente,
    cliente_nome: item.cliente_nome || cliente.razao_social,
    id_tecnico_atribuido: id_tecnico,
    tecnico: id_tecnico !== null ? tecnicos.find((t) => Number(t.id_tecnico) === id_tecnico) : undefined,
    status: item.status as StatusChamado,
    is_cancelled: item.is_cancelled === true,
    motivo_cancelamento: item.motivo_cancelamento ?? null,
    cancelado_em: item.cancelado_em ?? null,
    cancelado_por: item.cancelado_por ?? null,
    data_abertura: item.data_abertura || '',
    data_agendamento: item.data_agendamento ?? null,
    data_conclusao: item.data_conclusao ?? null,
    descricao_cliente: item.descricao_cliente || '',
    pedido: item.pedido ?? null,
    em_garantia: item.em_garantia !== false,
    equipamentos: Array.isArray(item.equipamentos) ? item.equipamentos : [],
    visitas: Array.isArray(item.visitas) ? item.visitas : [],
  };
}

export class ChamadoService {
  // --- Sessão ---
  static getUsuarioLogado(): UsuarioSessao | null {
    const token = apiClient.getToken();
    if (!token) return null;
    const dados = apiClient.decodeToken(token);
    if (!dados) {
      apiClient.clearToken();
      return null;
    }
    return {
      id_tecnico: dados.user_id,
      email: dados.sub,
      nome: nomeAPartirDoEmail(dados.sub),
      role: dados.role,
    };
  }

  static async login(username: string, password: string): Promise<UsuarioSessao> {
    await apiClient.login(username, password);
    const usuario = this.getUsuarioLogado();
    if (!usuario) {
      apiClient.clearToken();
      throw new Error('O servidor retornou um token inválido.');
    }
    return usuario;
  }

  /** Nome oficial via GET /api/auth/me. Em qualquer falha (ex.: rota ainda ausente) mantém o nome derivado do JWT. */
  static async atualizarPerfil(usuario: UsuarioSessao): Promise<UsuarioSessao> {
    try {
      const me = await apiClient.getMe();
      return me?.nome ? { ...usuario, nome: me.nome } : usuario;
    } catch {
      return usuario;
    }
  }

  static logout(): void {
    apiClient.clearToken();
  }

  // --- Clientes ---
  static listarClientes(): Promise<Cliente[]> {
    return apiClient.getClientes();
  }

  static async salvarCliente(dados: Partial<Cliente>): Promise<Cliente> {
    const payload = {
      razao_social: (dados.razao_social || '').trim(),
      codigo: Number(dados.codigo),
      contato_principal_nome: dados.contato_principal_nome || undefined,
      contato_principal_telefone: dados.contato_principal_telefone || undefined,
      telefone: (dados.telefone || '').trim(),
      endereco: (dados.endereco || '').trim(),
      numero: (dados.numero || '').trim(),
      bairro: (dados.bairro || '').trim(),
      cidade: (dados.cidade || '').trim(),
      uf: (dados.uf || '').trim().toUpperCase(),
      is_active: dados.is_active !== false,
    };
    if (dados.id_cliente) return apiClient.updateCliente(dados.id_cliente, payload);
    return apiClient.createCliente(payload);
  }

  static desativarCliente(id: number): Promise<void> {
    return apiClient.desativarCliente(id);
  }

  static async reativarCliente(id: number): Promise<void> {
    await apiClient.updateCliente(id, { is_active: true });
  }

  // --- Técnicos ---
  static listarTecnicos(): Promise<Tecnico[]> {
    return apiClient.getTecnicos();
  }

  static async salvarTecnico(dados: TecnicoPayload & { id_tecnico?: number }): Promise<Tecnico> {
    const { id_tecnico, ...payload } = dados;
    if (id_tecnico) return apiClient.updateTecnico(id_tecnico, payload);
    return apiClient.createTecnico(payload);
  }

  static desativarTecnico(id: number): Promise<void> {
    return apiClient.desativarTecnico(id);
  }

  static async reativarTecnico(id: number): Promise<void> {
    await apiClient.updateTecnico(id, { is_active: true });
  }

  // --- Ordens de serviço ---
  /** Lista as OS ativas (`cancelled=false`) ou canceladas (`cancelled=true`). Lança erro em qualquer falha. */
  static async listarChamados(
    cancelled: boolean,
    clientes: Cliente[],
    tecnicos: Tecnico[]
  ): Promise<OrdemServico[]> {
    const lista = await apiClient.getChamados(cancelled);
    if (!Array.isArray(lista)) {
      throw new Error('Resposta inesperada da API ao listar ordens de serviço.');
    }
    return lista.map((item) => normalizarChamado(item, clientes, tecnicos));
  }

  /**
   * Cria a OS. Sem técnico → "Pendente"; com técnico → "Agendado" (decidido pelo servidor, RN-10).
   * v0.5 (RN-41): `equipamentos[]` é obrigatório (mín. 1: modelo ativo do catálogo + série digitada). O painel NUNCA
   * cria visita nem inventa série/defeito: a visita nasce no servidor ao entrar em "Agendado" (RN-11a).
   */
  static criarOrdemServico(dados: ChamadoCreatePayload): Promise<Record<string, any>> {
    const equipamentos = (dados.equipamentos || []).map((e) => ({
      id_equipamento_modelo: Number(e.id_equipamento_modelo),
      numero_serie: e.numero_serie.trim(),
    }));
    if (equipamentos.length === 0) {
      return Promise.reject(new Error('Informe ao menos um equipamento (modelo e número de série).'));
    }
    return apiClient.createChamado({
      id_cliente: Number(dados.id_cliente),
      descricao_cliente: dados.descricao_cliente.trim(),
      id_tecnico_atribuido: dados.id_tecnico_atribuido ? Number(dados.id_tecnico_atribuido) : null,
      data_agendamento: dados.data_agendamento || null,
      pedido: dados.pedido?.trim() || null,
      em_garantia: dados.em_garantia !== false,
      equipamentos,
    });
  }

  /** Edição administrativa: descrição, pedido e garantia. Data e técnico têm ações próprias (reagendar/atribuir). */
  static atualizarOrdemServico(
    id_os: number,
    dados: { descricao_cliente: string; pedido?: string | null; em_garantia: boolean }
  ): Promise<Record<string, any>> {
    return apiClient.updateChamado(id_os, {
      descricao_cliente: dados.descricao_cliente.trim(),
      pedido: dados.pedido?.trim() || null,
      em_garantia: dados.em_garantia,
    });
  }

  static atribuirTecnico(id_os: number, id_tecnico: number): Promise<Record<string, any>> {
    return apiClient.atribuirTecnico(id_os, Number(id_tecnico));
  }

  static cancelarChamado(id_os: number, motivo: string): Promise<Record<string, any>> {
    return apiClient.cancelarChamado(id_os, motivo.trim());
  }

  static reagendarChamado(id_os: number, data_visita: string): Promise<Record<string, any>> {
    return apiClient.reagendarChamado(id_os, data_visita);
  }

  static pausarVisita(id_os: number, id_visita: number, motivo: string, descricao?: string): Promise<Record<string, any>> {
    return apiClient.pausarVisita(id_os, id_visita, motivo, descricao);
  }

  static getEstadoVisita(id_os: number, id_visita: number): Promise<EstadoVisitaResponse> {
    return apiClient.getEstadoVisita(id_os, id_visita);
  }

  static calcularCustos(id_os: number): Promise<CustoTotalResponse> {
    return apiClient.getCustosChamado(id_os);
  }

  // --- Catálogo de modelos de equipamento ---
  /** `isActive` omitido lista todos. Lança erro em qualquer falha (sem dados de fallback, CA-05). */
  static listarModelos(isActive?: boolean): Promise<EquipamentoModelo[]> {
    return apiClient.getModelos(isActive);
  }

  static criarModelo(modelo: string): Promise<EquipamentoModelo> {
    return apiClient.createModelo(modelo.trim());
  }

  static renomearModelo(id: number, modelo: string): Promise<EquipamentoModelo> {
    return apiClient.updateModelo(id, { modelo: modelo.trim() });
  }

  /** DELETE = desativação lógica. */
  static desativarModelo(id: number): Promise<void> {
    return apiClient.desativarModelo(id);
  }

  static async reativarModelo(id: number): Promise<void> {
    await apiClient.updateModelo(id, { is_active: true });
  }

  // --- Equipamentos da OS ---
  static listarEquipamentosOS(id_os: number): Promise<OsEquipamento[]> {
    return apiClient.getEquipamentosOS(id_os);
  }

  static vincularEquipamento(id_os: number, dados: OsEquipamentoPayload): Promise<OsEquipamento> {
    return apiClient.addEquipamentoOS(id_os, {
      id_equipamento_modelo: Number(dados.id_equipamento_modelo),
      numero_serie: dados.numero_serie.trim(),
    });
  }

  static corrigirEquipamento(
    id_os: number,
    id_os_equipamento: number,
    dados: OsEquipamentoPayload
  ): Promise<OsEquipamento> {
    return apiClient.updateEquipamentoOS(id_os, id_os_equipamento, {
      id_equipamento_modelo: Number(dados.id_equipamento_modelo),
      numero_serie: dados.numero_serie.trim(),
    });
  }

  static removerEquipamento(id_os: number, id_os_equipamento: number): Promise<void> {
    return apiClient.removeEquipamentoOS(id_os, id_os_equipamento);
  }

  // --- Correção administrativa de OS Finalizada (RN-49) ---
  static listarFotosServico(id_os: number, id_visita: number, id_servico: number) {
    return apiClient.getFotosServico(id_os, id_visita, id_servico);
  }

  static enviarFotoCorrecao(
    id_os: number,
    id_visita: number,
    id_servico: number,
    tipo: 'defeito' | 'conserto',
    arquivo: File
  ) {
    return apiClient.uploadFotoServico(id_os, id_visita, id_servico, tipo, arquivo);
  }

  static removerFotoCorrecao(id_os: number, id_visita: number, id_servico: number, foto: FotoServico): Promise<void> {
    return apiClient.removerFotoServico(id_os, id_visita, id_servico, foto.id_foto);
  }

  static corrigirMateriais(id_os: number, id_visita: number, id_servico: number, materiais: MaterialUtilizado[]) {
    return apiClient.corrigirMateriaisServico(id_os, id_visita, id_servico, materiais);
  }
}
