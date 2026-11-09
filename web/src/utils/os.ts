import { OrdemServico, Visita } from '../types';
import { ApiError } from '../services/apiClient';

/** Base da API para montar URLs de arquivos (fotos/assinaturas servidas em /static). */
const API_BASE = ((import.meta as any).env?.VITE_API_URL as string) || '';

/**
 * Código amigável da OS (OS-AAAA-NNNN).
 * PENDÊNCIA DE DECISÃO (PR-16): hoje é montado no front e NÃO é persistido.
 * Se a API passar a devolver `codigo_os`, ele tem prioridade. O ano vem da data de abertura
 * (lida como texto, sem conversão de fuso).
 */
export function montarCodigoOS(idOs: number, dataAbertura?: string | null, codigoApi?: string | null): string {
  if (codigoApi) return codigoApi;
  const ano = dataAbertura && /^\d{4}/.test(dataAbertura) ? dataAbertura.slice(0, 4) : '----';
  return `OS-${ano}-${String(idOs).padStart(4, '0')}`;
}

/** Converte 'AAAA-MM-DD' (ou ISO) em Date local sem deslocamento de fuso para datas puras. */
export function parseData(value?: string | null): Date | null {
  if (!value) return null;
  const apenasData = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (apenasData) {
    return new Date(Number(apenasData[1]), Number(apenasData[2]) - 1, Number(apenasData[3]));
  }
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function formatData(value?: string | null, fallback = '—'): string {
  const d = parseData(value);
  if (!d) return fallback;
  return d.toLocaleDateString('pt-BR');
}

export function formatDataHora(value?: string | null, fallback = '—'): string {
  const d = parseData(value);
  if (!d) return fallback;
  return `${d.toLocaleDateString('pt-BR')} ${d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}`;
}

export function formatMoeda(value?: number | null): string {
  return Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

export function formatCpf(value?: string | null): string {
  const digits = (value || '').replace(/\D/g, '');
  if (digits.length !== 11) return value || '—';
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

/** Mascara o CPF (LGPD): ***.***.***-NN, mantendo só os dois últimos dígitos. */
export function mascararCpf(value?: string | null): string {
  const digits = (value || '').replace(/\D/g, '');
  if (digits.length !== 11) return value ? '***.***.***-**' : '—';
  return `***.***.***-${digits.slice(9)}`;
}

/** Data de hoje no formato AAAA-MM-DD (fuso local). */
export function hojeISO(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mm}-${dd}`;
}

/**
 * PONTO ÚNICO de resolução de URL de arquivo (fotos, comprovantes, assinaturas). Toda `<img src>` do painel passa por aqui.
 * URLs relativas devolvidas pela API (ex.: /static/uploads/...) usam a base da API.
 *
 * TODO (SEG-09 / PR-03 / A1): hoje o backend serve /static publicamente, então `<img src>` com URL direta funciona.
 * Quando o backend proteger os arquivos (bucket privado), trocar esta função por uma das opções:
 *  (a) URL assinada de curta duração emitida pela API (preferível: continua sendo `<img src>`), ou
 *  (b) fetch com `Authorization: Bearer` + `URL.createObjectURL(blob)` (exige tornar a função assíncrona/hook).
 * Nenhum outro ponto do painel deve montar URL de arquivo.
 */
export function resolverUrlArquivo(url?: string | null): string {
  if (!url) return '';
  if (/^(https?:|data:|blob:)/i.test(url)) return url;
  return `${API_BASE}${url.startsWith('/') ? '' : '/'}${url}`;
}

/** Mensagem legível de erro da API (inclui 409/422 do servidor). */
export function mensagemErro(err: unknown, padrao = 'Não foi possível concluir a operação.'): string {
  if (err instanceof ApiError) {
    if (err.status === 0) {
      return 'Não foi possível conectar à API. Verifique a conexão e tente novamente.';
    }
    if (err.status === 403) {
      return err.detail || 'Você não tem permissão para esta operação.';
    }
    // 404/409/410/422: o `detail` do servidor é a explicação (ex.: "OS sem equipamento vinculado"); só há texto próprio sem ele.
    if (!err.detail) {
      if (err.status === 404) return 'Registro não encontrado (pode ter sido removido).';
      if (err.status === 409) return 'A operação conflita com o estado atual da OS. Atualize e tente novamente.';
      if (err.status === 422) return 'Dados inválidos. Revise os campos e tente novamente.';
    }
    return err.detail || padrao;
  }
  if (err instanceof Error && err.message) return err.message;
  return padrao;
}

// --- Ações permitidas (apenas dicas de interface; o servidor é a autoridade — AR-02) ---

export function osTerminal(os: Pick<OrdemServico, 'status' | 'is_cancelled'>): boolean {
  return os.is_cancelled || os.status === 'Finalizado';
}

/** OS Finalizada ou já cancelada não pode ser cancelada (RN-12). */
export function podeCancelar(os: Pick<OrdemServico, 'status' | 'is_cancelled'>): boolean {
  return !osTerminal(os);
}

/** Visita mais recente da OS (maior id). */
export function visitaAtual(os: Pick<OrdemServico, 'visitas'>): Visita | undefined {
  if (!os.visitas || os.visitas.length === 0) return undefined;
  return [...os.visitas].sort((a, b) => b.id_visita - a.id_visita)[0];
}

export function idaIniciada(v?: Visita): boolean | null {
  if (!v) return null;
  return Boolean(
    v.ida_inicio_em ||
      v.hora_inicio_ida ||
      (v.km_inicio_ida !== null && v.km_inicio_ida !== undefined) ||
      v.foto_inicio_ida_url
  );
}

export interface PermissaoAcao {
  permitido: boolean;
  motivo?: string;
}

/** RF-13 / RN-14 / TR-04: reagendar só em "Aguardando Reagendamento" ou "Agendado" sem ida iniciada. */
export function permissaoReagendar(os: OrdemServico): PermissaoAcao {
  if (os.is_cancelled) return { permitido: false, motivo: 'OS cancelada não pode ser reagendada.' };
  switch (os.status) {
    case 'Aguardando Reagendamento':
      return { permitido: true };
    case 'Agendado': {
      // A visita é criada pelo servidor ao entrar em Agendado. Se a lista de visitas veio e está vazia,
      // não há visita para reagendar.
      if (Array.isArray(os.visitas) && os.visitas.length === 0) {
        return { permitido: false, motivo: 'OS sem visita; o servidor cria ao atribuir.' };
      }
      const iniciada = idaIniciada(visitaAtual(os));
      if (iniciada) {
        return { permitido: false, motivo: 'O técnico já iniciou o deslocamento de ida; não é possível reagendar.' };
      }
      return { permitido: true };
    }
    case 'Pausado':
      return {
        permitido: false,
        motivo: 'OS pausada: o técnico precisa finalizar o deslocamento de volta. Depois a OS ficará em "Aguardando Reagendamento".',
      };
    case 'Pendente':
      return { permitido: false, motivo: 'Atribua um técnico antes de agendar.' };
    case 'Em Atendimento':
      return { permitido: false, motivo: 'OS em atendimento: pause e aguarde o técnico finalizar a volta.' };
    case 'Finalizado':
      return { permitido: false, motivo: 'OS finalizada não pode ser reagendada.' };
    default:
      return { permitido: false, motivo: 'Status não permite reagendamento.' };
  }
}

/** RN-30: admin só pausa com a visita em atendimento e não finalizada. */
export function permissaoPausar(os: OrdemServico): PermissaoAcao {
  if (os.is_cancelled) return { permitido: false, motivo: 'OS cancelada.' };
  if (os.status !== 'Em Atendimento') {
    return { permitido: false, motivo: 'Só é possível pausar uma OS com a visita em atendimento.' };
  }
  const v = visitaAtual(os);
  if (!v) return { permitido: false, motivo: 'Nenhuma visita encontrada para esta OS.' };
  if (v.servico_finalizado) return { permitido: false, motivo: 'A visita já foi finalizada.' };
  return { permitido: true };
}

/**
 * RN-45: o admin só edita os equipamentos da OS (adicionar, corrigir modelo/série, remover) enquanto o atendimento
 * não começou: Pendente, Agendado ou Aguardando Reagendamento. O servidor é a autoridade (409 com `detail`).
 */
export function permissaoEditarEquipamentos(os: Pick<OrdemServico, 'status' | 'is_cancelled'>): PermissaoAcao {
  if (os.is_cancelled) return { permitido: false, motivo: 'OS cancelada: equipamentos somente para leitura.' };
  if (os.status === 'Pendente' || os.status === 'Agendado' || os.status === 'Aguardando Reagendamento') {
    return { permitido: true };
  }
  if (os.status === 'Finalizado') {
    return {
      permitido: false,
      motivo:
        'OS finalizada: modelo e número de série não são editáveis (RN-49). Só é possível corrigir fotos e materiais, na seção "Correção administrativa".',
    };
  }
  return {
    permitido: false,
    motivo:
      'O atendimento já começou: os equipamentos ficam travados do início do atendimento até a finalização (RN-45) para não alterar o escopo em campo.',
  };
}

/** Atribuir/trocar técnico: somente Pendente, Agendado e Aguardando Reagendamento (o servidor valida). */
export function permissaoAtribuir(os: Pick<OrdemServico, 'status' | 'is_cancelled'>): PermissaoAcao {
  if (os.is_cancelled) return { permitido: false, motivo: 'OS cancelada.' };
  if (os.status === 'Pendente' || os.status === 'Agendado' || os.status === 'Aguardando Reagendamento') {
    return { permitido: true };
  }
  return {
    permitido: false,
    motivo: 'Só é possível atribuir ou trocar o técnico em OS Pendente, Agendado ou Aguardando Reagendamento.',
  };
}
