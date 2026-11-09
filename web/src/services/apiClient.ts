/**
 * Cliente HTTP do painel para a API FastAPI do Fast Ariam (SDD v0.3, seção 6).
 * Usa a base VITE_API_URL ou, se vazia, o proxy /api do Vite (127.0.0.1:8000).
 *
 * Contrato fixo: sem tentativas alternativas (PATCH→PUT, com/sem barra final) e sem dados de fallback.
 * Rotas de coleção terminam em barra ('/api/tecnicos/', '/api/clientes/', '/api/chamados/');
 * rotas de item não ('/api/tecnicos/{id}').
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
  Tecnico,
  UserRole,
} from '../types';

// Sessão em sessionStorage (PR-17 / SEG-04): some ao fechar a aba e não persiste entre sessões do navegador.
// PENDÊNCIA: cookie HttpOnly (a melhor opção contra XSS) exige mudança no backend (SEG-04).
const TOKEN_KEY = 'fast_ariam_jwt_token';
const BASE_URL = ((import.meta as any).env?.VITE_API_URL as string) || '';

export interface ApiTokenResponse {
  access_token: string;
  token_type: string;
}

export interface UserTokenPayload {
  sub: string;
  user_id: number;
  role: UserRole;
  exp?: number;
}

/** SHA-256 (hex minúsculo) dos bytes do arquivo, calculado no navegador (exige contexto seguro: HTTPS ou localhost). */
async function sha256Hex(arquivo: Blob): Promise<string> {
  if (!globalThis.crypto?.subtle) {
    throw new ApiError(0, 'Este navegador não permite calcular o hash do arquivo (use HTTPS).');
  }
  const digest = await globalThis.crypto.subtle.digest('SHA-256', await arquivo.arrayBuffer());
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

function lerArmazenamento(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

/** Dados do corpo de criação/edição de técnico (contrato 6.3.1). */
export interface TecnicoPayload {
  nome?: string;
  cnpj?: string;
  cpf?: string;
  inscricao_estadual?: string;
  email?: string;
  telefone?: string;
  password?: string;
  role?: UserRole;
  is_active?: boolean;
  dados_bancarios?: { banco: string; agencia: string; conta: string; pix?: string };
}

export type ClientePayload = Omit<Cliente, 'id_cliente'>;

/** Equipamento a vincular (modelo ATIVO do catálogo + série). Corpo de POST /chamados/{id}/equipamentos e item de `equipamentos[]`. */
export interface OsEquipamentoPayload {
  id_equipamento_modelo: number;
  numero_serie: string;
}

export interface ChamadoCreatePayload {
  id_cliente: number;
  descricao_cliente: string;
  id_tecnico_atribuido?: number | null;
  data_agendamento?: string | null;
  pedido?: string | null;
  em_garantia?: boolean;
  /** v0.5 (RN-41): obrigatório, mínimo 1. A OS nunca é criada sem equipamento (422). */
  equipamentos: OsEquipamentoPayload[];
}

/** Campos administrativos editáveis por PATCH. NUNCA enviar `status` (SDD 6.5.2). */
export interface ChamadoUpdatePayload {
  id_tecnico_atribuido?: number;
  descricao_cliente?: string;
  pedido?: string | null;
  em_garantia?: boolean;
}

/** Traduz as mensagens genéricas mais comuns do Pydantic (422); o restante do `detail` é mostrado como veio. */
function traduzirMensagemValidacao(msg: string): string {
  if (/^Field required$/i.test(msg)) return 'campo obrigatório.';
  if (/at least 1 item/i.test(msg)) return 'informe ao menos 1 item.';
  if (/at least 1 character/i.test(msg)) return 'não pode ficar vazio.';
  const max = /at most (\d+) character/i.exec(msg);
  if (max) return `no máximo ${max[1]} caracteres.`;
  return msg;
}

class ApiClient {
  private token: string | null = lerArmazenamento();
  private onUnauthorizedCallback: (() => void) | null = null;

  constructor() {
    // Remove token legado que ficava em localStorage (exposição prolongada em caso de XSS).
    try {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem('fast_ariam_current_user');
      localStorage.removeItem('fast_ariam_auth_user_v1');
      localStorage.removeItem('fast_tecnicos_cache');
      localStorage.removeItem('fast_chamados_cache');
      localStorage.removeItem('fast_ariam_chamados_cache_v2');
    } catch {
      // armazenamento indisponível: nada a limpar
    }
  }

  setOnUnauthorized(cb: (() => void) | null): void {
    this.onUnauthorizedCallback = cb;
  }

  // --- Sessão ---
  getToken(): string | null {
    if (!this.token) this.token = lerArmazenamento();
    if (this.token) {
      const decoded = this.decodeToken(this.token);
      if (!decoded || (decoded.exp && decoded.exp * 1000 < Date.now())) {
        this.clearToken();
        return null;
      }
    }
    return this.token;
  }

  private setToken(token: string): void {
    this.token = token;
    try {
      sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
      // sem armazenamento: a sessão vale apenas em memória
    }
  }

  clearToken(): void {
    this.token = null;
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      // ignora
    }
  }

  decodeToken(token: string): UserTokenPayload | null {
    try {
      const parts = token.split('.');
      if (parts.length !== 3) return null;
      const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
      const json = decodeURIComponent(
        atob(base64)
          .split('')
          .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
          .join('')
      );
      return JSON.parse(json) as UserTokenPayload;
    } catch {
      return null;
    }
  }

  // --- Requisição base ---
  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    { semRedirecionarEm401 = false }: { semRedirecionarEm401?: boolean } = {}
  ): Promise<T> {
    const headers = new Headers(options.headers || {});
    const token = this.getToken();
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    if (options.body && !(options.body instanceof URLSearchParams) && !(options.body instanceof FormData)) {
      if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
    }

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}${endpoint}`, { ...options, headers });
    } catch (e: any) {
      throw new ApiError(0, e?.message || 'Falha de conexão com a API.');
    }

    if (response.status === 204) return null as unknown as T;

    const contentType = response.headers.get('content-type') || '';
    let data: any = null;
    try {
      data = contentType.includes('application/json') ? await response.json() : await response.text();
    } catch {
      data = null;
    }

    if (!response.ok) {
      // 401 = token ausente/inválido/expirado ou usuário desativado: encerra a sessão local.
      if (response.status === 401 && !semRedirecionarEm401) {
        this.clearToken();
        this.onUnauthorizedCallback?.();
      }
      throw new ApiError(response.status, this.extrairDetalhe(data, response.status));
    }

    return data as T;
  }

  private extrairDetalhe(data: any, status: number): string {
    if (data && typeof data === 'object') {
      if (typeof data.detail === 'string') return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail
          .map((err: any) => {
            const campo = Array.isArray(err.loc) ? err.loc.filter((p: unknown) => p !== 'body').join('.') : '';
            // Pydantic prefixa erros de validadores customizados com "Value error, ": removido para o usuário final.
            const msg = traduzirMensagemValidacao(
              typeof err.msg === 'string' ? err.msg.replace(/^Value error,\s*/i, '') : ''
            );
            return campo ? `${campo}: ${msg}` : msg || JSON.stringify(err);
          })
          .join('; ');
      }
      return JSON.stringify(data);
    }
    if (typeof data === 'string' && data.trim() && !data.trim().startsWith('<')) return data;
    return `Erro ${status} ao processar a requisição.`;
  }

  // --- Autenticação ---
  async login(username: string, password: string): Promise<ApiTokenResponse> {
    const body = new URLSearchParams();
    body.append('username', username);
    body.append('password', password);
    const data = await this.request<ApiTokenResponse>(
      '/api/auth/login',
      { method: 'POST', body, headers: { 'Content-Type': 'application/x-www-form-urlencoded' } },
      { semRedirecionarEm401: true }
    );
    if (data?.access_token) this.setToken(data.access_token);
    return data;
  }

  /** Perfil do usuário logado (GET /api/auth/me — SDD 6.2). Pode não existir ainda no backend: o chamador trata a falha. */
  getMe(): Promise<{ id_tecnico: number; nome: string; email: string; role: UserRole; is_active: boolean }> {
    return this.request('/api/auth/me');
  }

  // --- Técnicos (admin) ---
  getTecnicos(isActive?: boolean): Promise<Tecnico[]> {
    const query = isActive !== undefined ? `?is_active=${isActive}` : '';
    return this.request<Tecnico[]>(`/api/tecnicos/${query}`);
  }

  createTecnico(payload: TecnicoPayload): Promise<Tecnico> {
    return this.request<Tecnico>('/api/tecnicos/', { method: 'POST', body: JSON.stringify(payload) });
  }

  updateTecnico(id: number, payload: TecnicoPayload): Promise<Tecnico> {
    return this.request<Tecnico>(`/api/tecnicos/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
  }

  /** DELETE = desativação lógica + invalidação de sessões (SDD 6.3). */
  desativarTecnico(id: number): Promise<void> {
    return this.request<void>(`/api/tecnicos/${id}`, { method: 'DELETE' });
  }

  // --- Clientes (admin) ---
  getClientes(isActive?: boolean): Promise<Cliente[]> {
    const query = isActive !== undefined ? `?is_active=${isActive}` : '';
    return this.request<Cliente[]>(`/api/clientes/${query}`);
  }

  createCliente(payload: ClientePayload): Promise<Cliente> {
    return this.request<Cliente>('/api/clientes/', { method: 'POST', body: JSON.stringify(payload) });
  }

  updateCliente(id: number, payload: Partial<ClientePayload>): Promise<Cliente> {
    return this.request<Cliente>(`/api/clientes/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
  }

  /** DELETE = desativação lógica (RN-05). */
  desativarCliente(id: number): Promise<void> {
    return this.request<void>(`/api/clientes/${id}`, { method: 'DELETE' });
  }

  // --- Ordens de serviço ---
  getChamados(isCancelled: boolean): Promise<Array<Partial<OrdemServico> & Record<string, any>>> {
    return this.request(`/api/chamados/?is_cancelled=${isCancelled}`);
  }

  createChamado(payload: ChamadoCreatePayload): Promise<Record<string, any>> {
    return this.request('/api/chamados/', { method: 'POST', body: JSON.stringify(payload) });
  }

  updateChamado(id: number, payload: ChamadoUpdatePayload): Promise<Record<string, any>> {
    return this.request(`/api/chamados/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
  }

  /** Atribuição envia SOMENTE o técnico; o servidor define o status (RN-11). */
  atribuirTecnico(id: number, idTecnico: number): Promise<Record<string, any>> {
    return this.request(`/api/chamados/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ id_tecnico_atribuido: idTecnico }),
    });
  }

  cancelarChamado(id: number, motivo: string): Promise<Record<string, any>> {
    return this.request(`/api/chamados/${id}/cancelar`, { method: 'POST', body: JSON.stringify({ motivo }) });
  }

  reagendarChamado(id: number, dataVisita: string): Promise<Record<string, any>> {
    return this.request(`/api/chamados/${id}/reagendar`, {
      method: 'POST',
      body: JSON.stringify({ data_visita: dataVisita }),
    });
  }

  // --- Catálogo de modelos de equipamento (admin; SDD 6.13) ---
  getModelos(isActive?: boolean): Promise<EquipamentoModelo[]> {
    const query = isActive !== undefined ? `?is_active=${isActive}` : '';
    return this.request<EquipamentoModelo[]>(`/api/equipamentos/${query}`);
  }

  createModelo(modelo: string): Promise<EquipamentoModelo> {
    return this.request<EquipamentoModelo>('/api/equipamentos/', { method: 'POST', body: JSON.stringify({ modelo }) });
  }

  updateModelo(id: number, payload: { modelo?: string; is_active?: boolean }): Promise<EquipamentoModelo> {
    return this.request<EquipamentoModelo>(`/api/equipamentos/${id}`, { method: 'PATCH', body: JSON.stringify(payload) });
  }

  /** DELETE = desativação lógica (204). Reativar é PATCH { is_active: true }. */
  desativarModelo(id: number): Promise<void> {
    return this.request<void>(`/api/equipamentos/${id}`, { method: 'DELETE' });
  }

  // --- Equipamentos da OS (SDD 6.13) ---
  getEquipamentosOS(idOs: number): Promise<OsEquipamento[]> {
    return this.request<OsEquipamento[]>(`/api/chamados/${idOs}/equipamentos`);
  }

  addEquipamentoOS(idOs: number, payload: OsEquipamentoPayload): Promise<OsEquipamento> {
    return this.request<OsEquipamento>(`/api/chamados/${idOs}/equipamentos`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  updateEquipamentoOS(idOs: number, idOsEquipamento: number, payload: Partial<OsEquipamentoPayload>): Promise<OsEquipamento> {
    return this.request<OsEquipamento>(`/api/chamados/${idOs}/equipamentos/${idOsEquipamento}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  }

  removeEquipamentoOS(idOs: number, idOsEquipamento: number): Promise<void> {
    return this.request<void>(`/api/chamados/${idOs}/equipamentos/${idOsEquipamento}`, { method: 'DELETE' });
  }

  // --- Correção administrativa de OS Finalizada (RN-49) ---
  getFotosServico(
    idOs: number,
    idVisita: number,
    idServico: number
  ): Promise<{ fotos_defeito: FotoServico[]; fotos_conserto: FotoServico[] }> {
    return this.request(`/api/chamados/${idOs}/visitas/${idVisita}/servicos/${idServico}/fotos`);
  }

  async uploadFotoServico(
    idOs: number,
    idVisita: number,
    idServico: number,
    tipo: 'defeito' | 'conserto',
    arquivo: File
  ): Promise<{ status: string; url: string; tipo: string; id_foto?: number | null }> {
    const body = new FormData();
    body.append('tipo', tipo);
    body.append('sha256', await sha256Hex(arquivo)); // Integridade: o servidor recalcula e recusa (422) se divergir
    body.append('file', arquivo);
    return this.request(`/api/chamados/${idOs}/visitas/${idVisita}/servicos/${idServico}/upload-foto`, {
      method: 'POST',
      body,
    });
  }

  /** 409 se for a última foto do tipo daquele equipamento. */
  removerFotoServico(idOs: number, idVisita: number, idServico: number, idFoto: number): Promise<void> {
    return this.request<void>(`/api/chamados/${idOs}/visitas/${idVisita}/servicos/${idServico}/fotos/${idFoto}`, {
      method: 'DELETE',
    });
  }

  /** Admin em OS Finalizada: o corpo contém SOMENTE `materiais_utilizados` (qualquer outro campo = 422). */
  corrigirMateriaisServico(
    idOs: number,
    idVisita: number,
    idServico: number,
    materiais: MaterialUtilizado[]
  ): Promise<Record<string, any>> {
    return this.request(`/api/chamados/${idOs}/visitas/${idVisita}/servicos/${idServico}`, {
      method: 'PATCH',
      body: JSON.stringify({
        materiais_utilizados: materiais.map((m) => ({ nome: m.nome, quantidade: m.quantidade, valor: m.valor })),
      }),
    });
  }

  getCustosChamado(id: number): Promise<CustoTotalResponse> {
    return this.request<CustoTotalResponse>(`/api/chamados/${id}/custos`);
  }

  // --- Visitas ---
  getEstadoVisita(idOs: number, idVisita: number): Promise<EstadoVisitaResponse> {
    return this.request<EstadoVisitaResponse>(`/api/chamados/${idOs}/visitas/${idVisita}/estado`);
  }

  /** Baixa um arquivo protegido da API com o token (as rotas de arquivo exigem `Authorization`). */
  private async baixarBlob(caminho: string, mensagemPadrao: string): Promise<Blob> {
    const token = this.getToken();
    let response: Response;
    try {
      response = await fetch(`${BASE_URL}${caminho}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    } catch (e: any) {
      throw new ApiError(0, e?.message || 'Falha de conexão com a API.');
    }
    if (!response.ok) {
      let detail = mensagemPadrao;
      try {
        const corpo = await response.json();
        if (typeof corpo?.detail === 'string') detail = corpo.detail;
      } catch {
        /* corpo sem JSON: mantém a mensagem padrão */
      }
      throw new ApiError(response.status, detail);
    }
    return response.blob();
  }

  /** Imagem da assinatura do cliente (cifrada em disco; a API a decifra e só entrega a admin/técnico da OS). */
  baixarAssinatura(idOs: number, idVisita: number): Promise<Blob> {
    return this.baixarBlob(`/api/chamados/${idOs}/visitas/${idVisita}/assinatura`, 'Não foi possível carregar a assinatura.');
  }

  /**
   * Foto/comprovante da OS vindo do armazenamento privado. `url` é a referência devolvida pela API (`/static/uploads/...`),
   * que NÃO é mais um endereço público: a API confere se o arquivo pertence a esta OS antes de entregá-lo.
   */
  baixarArquivo(idOs: number, url: string): Promise<Blob> {
    return this.baixarBlob(
      `/api/chamados/${idOs}/arquivos/conteudo?url=${encodeURIComponent(url)}`,
      'Não foi possível carregar a foto.'
    );
  }

  /** Pausa pelo administrador (RN-30). `descricao` obrigatória quando motivo = "Outro" (validado também no servidor). */
  pausarVisita(idOs: number, idVisita: number, motivo: string, descricao?: string): Promise<Record<string, any>> {
    const body: { motivo: string; descricao?: string } = { motivo };
    if (descricao && descricao.trim()) body.descricao = descricao.trim();
    return this.request(`/api/chamados/${idOs}/visitas/${idVisita}/pausar`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  }
}

export const apiClient = new ApiClient();
