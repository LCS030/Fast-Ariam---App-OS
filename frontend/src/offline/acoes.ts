// Acoes offline-first do fluxo da visita (AR-04).
//
// Toda acao: (1) valida no aparelho contra o ESTADO LOCAL (so conveniencia; o servidor decide),
// (2) copia as imagens para o armazenamento privado do app, (3) grava arquivos + eventos na
// outbox numa unica transacao SQLite e SO ENTAO (4) tenta sincronizar, sem aguardar.
// O horario da acao (`ocorrido_em`) e o do relogio do aparelho, com fuso (RN-35).
import type { ArquivoImagem } from "@/api/arquivo";
import type { ServicoPatch } from "@/api/servico";
import { agoraIso } from "@/api/visitas";
import { resolucaoConsertoValida, type FotoCapturada } from "@/utils/camera";
import { validarPausa } from "@/utils/pausa";
import { cpfValido, soDigitos } from "@/utils/validators";
import { copiarParaFila, salvarAssinaturaNaFila } from "./arquivos";
import { sha256DoArquivo } from "./hash";
import { obterOsLocal, OsLocal, rotuloDaOs } from "./cacheOS";
import { atualizarEvento, gravarAcao, NovoArquivo, NovoEvento, novoUuid, obterEvento } from "./outbox";
import { exigirSessaoOperante } from "./sessao";
import { atualizarContagens } from "./status";
import { dispararSync } from "./sync";
import { ErroOffline, TipoArquivo, TipoEvento } from "./tipos";

export interface Contexto {
  idOs: number;
  idVisita: number;
}

interface Preparada {
  idTecnico: number;
  os: OsLocal;
  rotulo: string;
}

async function preparar(ctx: Contexto): Promise<Preparada> {
  const sessao = await exigirSessaoOperante(); // 24 h desde o ultimo login online (RN-39)
  const os = await obterOsLocal(ctx.idOs);
  if (!os) {
    throw new ErroOffline(
      "OS_INDISPONIVEL",
      "Esta OS não está salva no aparelho. Conecte-se e sincronize para baixá-la."
    );
  }
  if (!os.visita || os.visita.id_visita !== ctx.idVisita || !os.estado) {
    throw new ErroOffline(
      "VISITA_INDISPONIVEL",
      "Esta visita não é mais a vigente da OS. Volte à lista e abra a OS novamente."
    );
  }
  return { idTecnico: sessao.idTecnico, os, rotulo: await rotuloDaOs(sessao.idTecnico, ctx.idOs) };
}

function exigir(condicao: boolean, codigo: string, mensagem: string): void {
  if (!condicao) throw new ErroOffline(codigo, mensagem);
}

/** Grava a acao e dispara o envio. Se gravar falhar, NADA foi aceito (a tela mantem os dados). */
async function registrar(
  p: Preparada,
  arquivos: NovoArquivo[],
  eventos: NovoEvento[]
): Promise<void> {
  await gravarAcao(p.idTecnico, arquivos, eventos);
  await atualizarContagens();
  dispararSync();
}

function evento(
  ctx: Contexto,
  p: Preparada,
  tipo: TipoEvento,
  payload: Record<string, unknown>,
  ocorridoEm: string = agoraIso()
): NovoEvento {
  return {
    client_event_id: novoUuid(),
    tipo,
    id_os: ctx.idOs,
    id_visita: ctx.idVisita,
    ocorrido_em: ocorridoEm,
    payload,
    rotulo_os: p.rotulo,
  };
}

async function arquivoParaFila(
  ctx: Contexto,
  tipo: TipoArquivo,
  imagem: ArquivoImagem
): Promise<NovoArquivo> {
  const id = novoUuid();
  const caminho = await copiarParaFila(imagem, id);
  const sha256 = await sha256DoArquivo(caminho); // hash na CAPTURA: prova que o arquivo nao mudou durante a fila
  return {
    client_file_id: id,
    tipo_arquivo: tipo,
    caminho_local: caminho,
    mime: imagem.mime,
    sha256,
    id_os: ctx.idOs,
    id_visita: ctx.idVisita,
  };
}

// ---------------------------------------------------------------------------------------------
// Deslocamento
// ---------------------------------------------------------------------------------------------
export async function registrarInicioDeslocamento(
  ctx: Contexto,
  tipo: "ida" | "volta",
  km: number,
  foto: ArquivoImagem
): Promise<void> {
  const p = await preparar(ctx);
  const e = p.os.estado!;
  exigir(
    tipo === "ida" ? e.pode_iniciar_deslocamento_ida : e.pode_iniciar_deslocamento_volta,
    "ACAO_INDISPONIVEL",
    `O deslocamento de ${tipo} não pode ser iniciado agora.`
  );
  const arq = await arquivoParaFila(ctx, "foto_deslocamento", foto);
  const ev = evento(
    ctx,
    p,
    tipo === "ida" ? "deslocamento_ida_iniciado" : "deslocamento_volta_iniciado",
    { km_inicio: km, foto_ref: arq.client_file_id }
  );
  await registrar(p, [arq], [ev]);
}

export async function registrarFimDeslocamento(
  ctx: Contexto,
  tipo: "ida" | "volta",
  km: number,
  foto: ArquivoImagem
): Promise<void> {
  const p = await preparar(ctx);
  const e = p.os.estado!;
  exigir(
    tipo === "ida" ? e.pode_finalizar_deslocamento_ida : e.pode_finalizar_deslocamento_volta,
    "ACAO_INDISPONIVEL",
    `O deslocamento de ${tipo} não pode ser finalizado agora.`
  );
  const kmInicio = tipo === "ida" ? p.os.kmInicio.ida : p.os.kmInicio.volta;
  exigir(
    kmInicio === null || km >= kmInicio,
    "KM_INVALIDO",
    `O KM final não pode ser menor que o KM inicial (${kmInicio}).`
  );
  const arq = await arquivoParaFila(ctx, "foto_deslocamento", foto);
  const ev = evento(
    ctx,
    p,
    tipo === "ida" ? "deslocamento_ida_finalizado" : "deslocamento_volta_finalizado",
    { km_fim: km, foto_ref: arq.client_file_id }
  );
  await registrar(p, [arq], [ev]);
}

// ---------------------------------------------------------------------------------------------
// Atendimento
// ---------------------------------------------------------------------------------------------
/** Foto de defeito (antes ou durante o atendimento) ou de conserto (RN-21 validada na captura). */
export async function registrarFotoServico(
  ctx: Contexto,
  idServico: number,
  tipo: "defeito" | "conserto",
  foto: FotoCapturada
): Promise<void> {
  const p = await preparar(ctx);
  const e = p.os.estado!;
  if (tipo === "defeito") {
    exigir(
      e.pode_registrar_foto_defeito,
      "ACAO_INDISPONIVEL",
      "A foto do defeito não pode ser registrada agora."
    );
  } else {
    exigir(
      !!e.atendimento_em_andamento && !e.is_os_pausada,
      "ACAO_INDISPONIVEL",
      "A foto do conserto só pode ser registrada com o atendimento em andamento e a OS sem pausa."
    );
    // Revalida 960x1280 (qualquer orientacao) logo antes de aceitar; nada e reduzido (RN-37).
    exigir(
      resolucaoConsertoValida(foto.width, foto.height),
      "RESOLUCAO_INSUFICIENTE",
      "A foto do conserto precisa ter no mínimo 960x1280 px (retrato ou paisagem)."
    );
  }
  exigir(
    e.equipamentos.some((q) => q.id_servico === idServico),
    "EQUIPAMENTO_INVALIDO",
    "Equipamento não encontrado nesta visita."
  );
  const arq = await arquivoParaFila(ctx, tipo === "defeito" ? "foto_defeito" : "foto_conserto", foto);
  const ev = evento(ctx, p, "foto_servico", {
    id_servico: idServico,
    tipo,
    foto_ref: arq.client_file_id,
  });
  await registrar(p, [arq], [ev]);
}

export async function registrarInicioAtendimento(ctx: Contexto): Promise<void> {
  const p = await preparar(ctx);
  const e = p.os.estado!;
  exigir(
    e.pode_iniciar_atendimento,
    "ACAO_INDISPONIVEL",
    e.bloqueio_iniciar_atendimento ?? "O atendimento não pode ser iniciado agora."
  );
  await registrar(p, [], [evento(ctx, p, "atendimento_iniciado", {})]);
}

function exigirAtendimentoAberto(e: NonNullable<OsLocal["estado"]>): void {
  exigir(
    !!e.atendimento_em_andamento && !e.is_os_pausada,
    "ACAO_INDISPONIVEL",
    "O registro do atendimento só pode ser alterado com o atendimento em andamento e a OS sem pausa."
  );
}

function payloadServico(idServico: number, patch: ServicoPatch): Record<string, unknown> {
  // Somente defeitos, descricoes e materiais; nunca modelo/serie/nome (422 no servidor).
  return { id_servico: idServico, ...patch };
}

export async function salvarRegistroServico(
  ctx: Contexto,
  idServico: number,
  patch: ServicoPatch
): Promise<void> {
  const p = await preparar(ctx);
  exigirAtendimentoAberto(p.os.estado!);
  await registrar(p, [], [evento(ctx, p, "servico_salvo", payloadServico(idServico, patch))]);
}

/** "Salvar conserto": grava os dados e marca o conserto (dois eventos, uma unica transacao local). */
export async function salvarConserto(
  ctx: Contexto,
  idServico: number,
  patch: ServicoPatch
): Promise<void> {
  const p = await preparar(ctx);
  exigirAtendimentoAberto(p.os.estado!);
  exigir(
    patch.defeitos_principais.length > 0,
    "DEFEITO_OBRIGATORIO",
    "Informe ao menos um defeito principal para salvar o conserto."
  );
  const t = agoraIso();
  await registrar(
    p,
    [],
    [
      evento(ctx, p, "servico_salvo", payloadServico(idServico, patch), t),
      evento(ctx, p, "conserto_salvo", { id_servico: idServico }, t),
    ]
  );
}

export async function registrarPausa(
  ctx: Contexto,
  motivo: string,
  descricao?: string
): Promise<void> {
  const invalido = validarPausa(motivo, descricao ?? "");
  if (invalido) throw new ErroOffline("PAUSA_INVALIDA", invalido);
  const p = await preparar(ctx);
  exigir(p.os.estado!.pode_pausar_os, "ACAO_INDISPONIVEL", "A OS não pode ser pausada agora.");
  const payload: Record<string, unknown> = { motivo };
  if (descricao && descricao.trim()) payload.descricao = descricao.trim();
  await registrar(p, [], [evento(ctx, p, "pausa_registrada", payload)]);
}

export async function registrarFimAtendimento(
  ctx: Contexto,
  dados: { nomeCliente: string; cpf: string; assinaturaBase64: string }
): Promise<void> {
  exigir(cpfValido(dados.cpf), "CPF_INVALIDO", "CPF inválido. Confira os 11 dígitos.");
  exigir(dados.nomeCliente.trim().length >= 2, "NOME_INVALIDO", "Informe o nome de quem assina.");
  const p = await preparar(ctx);
  const e = p.os.estado!;
  exigir(
    e.pode_finalizar_atendimento,
    "ACAO_INDISPONIVEL",
    e.bloqueio_finalizar_atendimento ?? "O atendimento não pode ser finalizado agora."
  );
  const id = novoUuid();
  const caminho = await salvarAssinaturaNaFila(dados.assinaturaBase64, id);
  const arq: NovoArquivo = {
    client_file_id: id,
    tipo_arquivo: "assinatura",
    caminho_local: caminho,
    mime: "image/png",
    sha256: await sha256DoArquivo(caminho),
    id_os: ctx.idOs,
    id_visita: ctx.idVisita,
  };
  const ev = evento(ctx, p, "atendimento_finalizado", {
    nome_cliente: dados.nomeCliente.trim(),
    documento_cliente: soDigitos(dados.cpf),
    assinatura_ref: id,
  });
  await registrar(p, [arq], [ev]);
}

// ---------------------------------------------------------------------------------------------
// Pedagio e frete (comprovante exige foto: comprovante_registrado sempre leva foto_ref)
// ---------------------------------------------------------------------------------------------
export async function registrarDespesas(
  ctx: Contexto,
  itens: { tipo: "pedagio" | "frete"; valor: number; foto: ArquivoImagem }[]
): Promise<void> {
  if (itens.length === 0) return;
  const p = await preparar(ctx);
  const e = p.os.estado!;
  exigir(
    e.visita_vigente !== false && !e.pode_concluir_chamado,
    "ACAO_INDISPONIVEL",
    "Esta visita já foi encerrada; pedágio e frete não podem mais ser registrados."
  );
  const arquivos: NovoArquivo[] = [];
  const eventos: NovoEvento[] = [];
  for (const item of itens) {
    const arq = await arquivoParaFila(
      ctx,
      item.tipo === "pedagio" ? "comprovante_pedagio" : "comprovante_frete",
      item.foto
    );
    arquivos.push(arq);
    eventos.push(
      evento(ctx, p, "comprovante_registrado", {
        tipo: item.tipo,
        valor: item.valor,
        foto_ref: arq.client_file_id,
      })
    );
  }
  await registrar(p, arquivos, eventos);
}

// ---------------------------------------------------------------------------------------------
// Rejeicoes (SY-08)
// ---------------------------------------------------------------------------------------------
/**
 * Reenvia uma acao rejeitada com NOVO client_event_id (o antigo permanece como historico, marcado
 * como tratado). Mantem o payload (os arquivos ja enviados continuam referenciados) e usa o
 * horario atual, para a acao ser processada DEPOIS da correcao (ex.: foto que faltava).
 */
export async function reenviarEventoRejeitado(clientEventId: string): Promise<void> {
  const sessao = await exigirSessaoOperante();
  const antigo = await obterEvento(clientEventId);
  if (!antigo || antigo.status !== "rejeitado" || antigo.id_tecnico !== sessao.idTecnico) {
    throw new ErroOffline("EVENTO_INVALIDO", "Esta ação não pode ser reenviada.");
  }
  const novo: NovoEvento = {
    client_event_id: novoUuid(),
    tipo: antigo.tipo,
    id_os: antigo.id_os,
    id_visita: antigo.id_visita,
    ocorrido_em: agoraIso(),
    payload: antigo.payload,
    rotulo_os: antigo.rotulo_os,
    reenvio_de: antigo.client_event_id,
  };
  await gravarAcao(sessao.idTecnico, [], [novo]);
  await atualizarEvento(antigo.client_event_id, { tratado: true });
  await atualizarContagens();
  dispararSync();
}

/** Tecnico ciente da rejeicao: some da lista de pendencias, mas a linha continua no banco. */
export async function dispensarRejeicao(clientEventId: string): Promise<void> {
  await atualizarEvento(clientEventId, { tratado: true });
  await atualizarContagens();
}
