"""
Sincronização offline (SDD 6.12, PRD RF-20..22 / RN-35..RN-38).

* Cada evento do aparelho passa pelos MESMOS serviços do fluxo online (SY-02), com o `ocorrido_em` do aparelho no lugar
  de "agora" e o mesmo usuário (técnico) - as regras de status, TR-12/TR-13, pausa e permissões valem iguais.
* Idempotência por `client_event_id` (SY-03). Transação POR EVENTO: a linha de `sync_evento` e o efeito do evento são
  confirmados juntos (a linha é adicionada à sessão antes do serviço, que confirma a transação). Rejeição desfaz o efeito e
  grava a rejeição numa transação própria (SY-06). Nada é descartado em silêncio.
* `ARQUIVO_AUSENTE` é TRANSITÓRIO: não é gravado, para o app reenviar o mesmo `client_event_id` depois do arquivo (SY-08).
* Conflito administrativo (SY-05/SY-09) rejeita o evento e leva a OS não finalizada a `Pendente`, sem técnico.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import IntegrityError

from app.core import crypto
from app.core.erros import ErroRegra
from app.models.sync_arquivo import SyncArquivo
from app.models.sync_evento import SyncEvento
from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado, validar_texto_armazenavel
from app.schemas.chamado import Chamado
from app.schemas.servico_equipamento import ServicoEquipamentoUpdate
from app.schemas.sync import EventoSync, LoteSync, ResultadoEvento
from app.schemas.visita import PausarPayload
from app.services import auditoria_service as auditoria
from app.services import chamado_service, servico_service, visita_service
from app.services.tempo import agora_utc

logger = logging.getLogger(__name__)

TOLERANCIA_RELOGIO = timedelta(minutes=2)  # SY-04

APLICADO, DUPLICADO, REJEITADO = "aplicado", "duplicado", "rejeitado"


class ArquivoAusente(Exception):
    """O arquivo referenciado ainda não foi recebido (transitório, SY-08)."""

    def __init__(self, ref):
        super().__init__(f"O arquivo '{ref}' ainda não foi enviado; envie-o e reenvie o evento.")


@dataclass
class Ctx:
    repo: SQLRepository
    usuario: dict
    chamado: Any
    visita: Any
    evento: EventoSync
    ocorrido: datetime
    payload: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------------------------
# Confidencialidade do payload gravado em sync_evento (SEG-22 ampliado, v0.7)
# ---------------------------------------------------------------------------------------------------------------------

# Chaves do payload com dado pessoal do cliente. A cifragem e POR CHAVE (nao por tipo de evento): `_persistir_rejeicao` e
# chamada tambem para tipo desconhecido e DEPENDENCIA_REJEITADA, antes de qualquer handler.
CHAVES_PESSOAIS_PAYLOAD = ("documento_cliente", "nome_cliente")

# Valor gravado (cifrado) quando nem o texto de recuperacao pode ser cifrado; nunca contem dado do aparelho.
_MARCADOR_INVALIDO = "[valor invalido descartado]"


def contexto_payload(chave: str, client_event_id) -> str:
    """AAD POR LINHA: `sync_evento.<chave>|<client_event_id>`. Um valor cifrado copiado para outro evento nao decifra."""
    return f"sync_evento.{chave}|{client_event_id}"


def _texto_para_cifrar(valor: Any) -> str:
    """
    Texto a cifrar para QUALQUER valor, sem nunca lancar: `str` segue como esta (surrogate isolado vira uma sequencia literal
    de escape, NUL passa); outros tipos viram JSON ASCII (`ensure_ascii=True`, `default=str`).
    """
    if isinstance(valor, str):
        return valor.encode("utf-8", "backslashreplace").decode("utf-8")
    return json.dumps(valor, ensure_ascii=True, default=str)


def cifrar_payload(payload: Dict[str, Any], client_event_id) -> Dict[str, Any]:
    """
    Devolve uma COPIA do payload com `documento_cliente`/`nome_cliente` cifrados (`enc1:...`, AAD por linha); o original
    (que alimenta o handler via `Ctx.payload`) nao e alterado. NUNCA lanca excecao por causa do valor - senao o evento nao
    seria gravado e a idempotencia (SY-03) quebraria:
      * ausente -> continua ausente; `None` -> continua `None` (nao ha dado pessoal a proteger);
      * `str` (inclusive vazia, com NUL ou surrogate isolado) -> cifrada (ver `_texto_para_cifrar`);
      * qualquer outro tipo (int, bool, float, dict, lista) -> JSON e entao cifrado. O evento sera rejeitado pelo handler
        (VALIDACAO), mas nada legivel e gravado;
      * se ainda assim falhar, grava o marcador fixo cifrado (ou, em ultimo caso, o marcador sem cifra: nao e dado pessoal).
    Sempre cifra, mesmo que o texto ja comece com `enc1:` (o aparelho nao e confiavel para dizer o que ja esta cifrado).
    """
    copia = dict(payload)
    for chave in CHAVES_PESSOAIS_PAYLOAD:
        if chave not in copia or copia[chave] is None:
            continue
        contexto = contexto_payload(chave, client_event_id)
        try:
            copia[chave] = crypto.cifrar(_texto_para_cifrar(copia[chave]), contexto)
        except Exception:  # noqa: BLE001 - propositalmente amplo: gravar o evento e mais importante que o valor
            logger.warning("Valor de '%s' nao pode ser cifrado no evento %s; gravado o marcador.", chave, client_event_id)
            try:
                copia[chave] = crypto.cifrar(_MARCADOR_INVALIDO, contexto)
            except Exception:  # noqa: BLE001
                copia[chave] = _MARCADOR_INVALIDO
    return copia


def decifrar_payload(payload: Dict[str, Any], client_event_id) -> Dict[str, Any]:
    """Inverso de `cifrar_payload` (copia). Valor que era nao-string volta como o TEXTO JSON serializado."""
    copia = dict(payload)
    for chave in CHAVES_PESSOAIS_PAYLOAD:
        if crypto.esta_cifrado(copia.get(chave)):
            copia[chave] = crypto.decifrar(copia[chave], contexto_payload(chave, client_event_id))
    return copia


# ---------------------------------------------------------------------------------------------------------------------
# Payloads por tipo de evento
# ---------------------------------------------------------------------------------------------------------------------

class _P(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Inicio(_P):
    km_inicio: int = Field(..., ge=0)
    foto_ref: Optional[UUID] = None


class _Fim(_P):
    km_fim: int = Field(..., ge=0)
    foto_ref: Optional[UUID] = None


class _AlvoServico(_P):
    id_servico: Optional[int] = None
    id_os_equipamento: Optional[int] = None


class _FotoServico(_AlvoServico):
    tipo: Literal["defeito", "conserto"]
    foto_ref: UUID


class _Comprovante(_P):
    tipo: Literal["pedagio", "frete"]
    valor: Optional[float] = Field(None, ge=0)
    foto_ref: UUID


class _Finalizar(_P):
    nome_cliente: str = Field(..., min_length=1, max_length=100)
    documento_cliente: str = Field(..., min_length=1, max_length=20)
    assinatura_ref: UUID

    @field_validator("nome_cliente", "documento_cliente", mode="after")
    @classmethod
    def _texto_armazenavel(cls, valor: str) -> str:  # NUL/surrogate isolado nao cabem no texto cifrado/PostgreSQL
        return validar_texto_armazenavel(valor)


# ---------------------------------------------------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------------------------------------------------

def _arquivo(ctx: Ctx, ref: UUID, tipo_esperado: str) -> SyncArquivo:
    """Arquivo já recebido em /api/sync/arquivos, do mesmo técnico e da mesma visita e do tipo esperado."""
    arq = ctx.repo.db.get(SyncArquivo, ref)
    if arq is None:
        raise ArquivoAusente(ref)
    if arq.id_tecnico != ctx.usuario["user_id"] or arq.id_visita != ctx.visita.id_visita:
        raise HTTPException(status_code=422, detail=f"O arquivo '{ref}' não pertence a esta visita.")
    if arq.tipo_arquivo != tipo_esperado:
        raise HTTPException(status_code=422,
                            detail=f"O arquivo '{ref}' é do tipo '{arq.tipo_arquivo}', esperado '{tipo_esperado}'.")
    return arq


def _resolver_servico(ctx: Ctx, alvo: _AlvoServico):
    """
    Registro de serviço da visita pelo `id_servico` ou `id_os_equipamento` (vindos do cache `minhas-os`).
    Equipamento/serviço que sumiu = o administrador removeu durante o período offline -> CONFLITO_ADMINISTRATIVO (SY-09).
    """
    repo = ctx.repo
    sumiu = ErroRegra(409, "O equipamento deste registro foi removido ou alterado pelo administrador.",
                      "CONFLITO_ADMINISTRATIVO")
    if alvo.id_servico is not None:
        servico = repo.get_servico_by_id(alvo.id_servico)
        if servico is None:
            raise sumiu
        if servico.id_visita != ctx.visita.id_visita:
            raise HTTPException(status_code=422, detail="O serviço informado não pertence a esta visita.")
        return servico
    if alvo.id_os_equipamento is not None:
        equipamento = repo.get_os_equipamento(alvo.id_os_equipamento)
        if equipamento is None:
            raise sumiu
        if equipamento.id_os != ctx.chamado.id_os:
            raise HTTPException(status_code=422, detail="O equipamento informado não pertence a esta OS.")
        for servico in repo.get_servicos_by_visita(ctx.visita.id_visita):
            if servico.id_os_equipamento == alvo.id_os_equipamento:
                return servico
        raise HTTPException(status_code=422, detail="Não há registro de serviço deste equipamento nesta visita.")
    raise HTTPException(status_code=422, detail="Informe id_servico ou id_os_equipamento.")


def _exigir_nao_finalizada(ctx: Ctx) -> None:
    if ctx.chamado.status == StatusChamado.FINALIZADO or ctx.chamado.status == StatusChamado.FINALIZADO.value:
        raise HTTPException(status_code=409, detail="OS 'Finalizado' não aceita novos arquivos nem alterações.")


# ---------------------------------------------------------------------------------------------------------------------
# Handlers (um por tipo de evento). Cada um confirma a transação (junto com a linha de sync_evento).
# ---------------------------------------------------------------------------------------------------------------------

def _h_iniciar_deslocamento(tipo: str) -> Callable[[Ctx], None]:
    def handler(ctx: Ctx) -> None:
        p = _Inicio(**ctx.payload)
        if p.foto_ref:
            arq = _arquivo(ctx, p.foto_ref, "foto_deslocamento")
            ctx.repo.set_arquivo_visita(ctx.visita.id_visita, f"foto_inicio_{tipo}_url", arq.url, arq.sha256, commit=False)
        visita_service.iniciar_deslocamento(ctx.repo, ctx.chamado, ctx.visita, tipo, p.km_inicio, ctx.ocorrido)
    return handler


def _h_finalizar_deslocamento(tipo: str) -> Callable[[Ctx], None]:
    def handler(ctx: Ctx) -> None:
        p = _Fim(**ctx.payload)
        if p.foto_ref:
            arq = _arquivo(ctx, p.foto_ref, "foto_deslocamento")
            ctx.repo.set_arquivo_visita(ctx.visita.id_visita, f"foto_fim_{tipo}_url", arq.url, arq.sha256, commit=False)
        visita_service.finalizar_deslocamento(ctx.repo, ctx.chamado, ctx.visita, tipo, p.km_fim, ctx.ocorrido,
                                              ctx.usuario)
    return handler


def _h_atendimento_iniciado(ctx: Ctx) -> None:
    visita_service.iniciar_atendimento(ctx.repo, ctx.chamado, ctx.visita, ctx.ocorrido, ctx.usuario)


def _h_servico_salvo(ctx: Ctx) -> None:
    alvo = _AlvoServico(**ctx.payload)
    campos = {k: v for k, v in ctx.payload.items() if k not in ("id_servico", "id_os_equipamento")}
    dados = ServicoEquipamentoUpdate(**campos).model_dump(exclude_unset=True)  # extra=forbid: série/nome -> VALIDACAO
    servico = _resolver_servico(ctx, alvo)
    if not dados:
        raise HTTPException(status_code=422, detail="Nenhum dado de serviço informado.")
    servico_service.atualizar_servico_tecnico(ctx.repo, ctx.chamado, ctx.visita, servico, dados, ctx.usuario)


def _h_conserto_salvo(ctx: Ctx) -> None:
    servico = _resolver_servico(ctx, _AlvoServico(**ctx.payload))
    servico_service.salvar_conserto(ctx.repo, ctx.chamado, ctx.visita, servico, ctx.ocorrido, ctx.usuario)


def _h_foto_servico(ctx: Ctx) -> None:
    p = _FotoServico(**ctx.payload)
    arq = _arquivo(ctx, p.foto_ref, f"foto_{p.tipo}")
    servico = _resolver_servico(ctx, p)
    _exigir_nao_finalizada(ctx)
    visita_service.exigir_visita_vigente(ctx.repo, ctx.chamado, ctx.visita)
    servico_service.exigir_fase_da_foto(ctx.chamado, ctx.visita, p.tipo)
    ctx.repo.add_servico_foto(servico.id_servico, p.tipo, arq.url, commit=False, sha256=arq.sha256)
    auditoria.registrar_acao(ctx.repo.db, id_os=ctx.chamado.id_os, usuario=ctx.usuario, acao=auditoria.UPLOAD_ARQUIVO,
                             payload={"id_visita": ctx.visita.id_visita, "id_servico": servico.id_servico,
                                      "campo": f"foto_{p.tipo}"})
    ctx.repo.commit()


def _h_comprovante(ctx: Ctx) -> None:
    p = _Comprovante(**ctx.payload)
    arq = _arquivo(ctx, p.foto_ref, f"comprovante_{p.tipo}")
    _exigir_nao_finalizada(ctx)
    visita_service.exigir_visita_vigente(ctx.repo, ctx.chamado, ctx.visita)
    campo = "valor_pedagio" if p.tipo == "pedagio" else "valor_frete_devolucao"
    if p.valor is not None:
        if ctx.visita.servico_finalizado and float(p.valor) != float(getattr(ctx.visita, campo) or 0):
            raise HTTPException(status_code=409,
                                detail=f"Visita encerrada: '{campo}' não pode mais ser alterado (custo já fechado).")
        ctx.repo.update_visita(ctx.visita.id_visita, {campo: p.valor}, commit=False)
    ctx.repo.add_comprovante(ctx.visita.id_visita, p.tipo, arq.url, commit=False, sha256=arq.sha256)
    auditoria.registrar_acao(ctx.repo.db, id_os=ctx.chamado.id_os, usuario=ctx.usuario, acao=auditoria.UPLOAD_ARQUIVO,
                             payload={"id_visita": ctx.visita.id_visita,
                                      "campo": f"comprovante_{p.tipo}_urls"})
    ctx.repo.commit()


def _h_pausa(ctx: Ctx) -> None:
    p = PausarPayload(motivo=ctx.payload.get("motivo"), descricao=ctx.payload.get("descricao"))
    visita_service.pausar(ctx.repo, ctx.chamado, ctx.visita, p.motivo.value, p.descricao, ctx.ocorrido, ctx.usuario)


def _h_atendimento_finalizado(ctx: Ctx) -> None:
    p = _Finalizar(**ctx.payload)
    arq = _arquivo(ctx, p.assinatura_ref, "assinatura")
    visita_service.finalizar_atendimento(ctx.repo, ctx.chamado, ctx.visita, p.nome_cliente.strip(),
                                         p.documento_cliente.strip(), None, ctx.ocorrido, ctx.usuario,
                                         assinatura_url=arq.url, assinatura_sha256=arq.sha256)


HANDLERS: Dict[str, Callable[[Ctx], None]] = {
    "deslocamento_ida_iniciado": _h_iniciar_deslocamento("ida"),
    "deslocamento_ida_finalizado": _h_finalizar_deslocamento("ida"),
    "atendimento_iniciado": _h_atendimento_iniciado,
    "servico_salvo": _h_servico_salvo,
    "conserto_salvo": _h_conserto_salvo,
    "foto_servico": _h_foto_servico,
    "comprovante_registrado": _h_comprovante,
    "pausa_registrada": _h_pausa,
    "atendimento_finalizado": _h_atendimento_finalizado,
    "deslocamento_volta_iniciado": _h_iniciar_deslocamento("volta"),
    "deslocamento_volta_finalizado": _h_finalizar_deslocamento("volta"),
}


# ---------------------------------------------------------------------------------------------------------------------
# Classificação das rejeições
# ---------------------------------------------------------------------------------------------------------------------

_PISTAS_VALIDACAO = ("obrigat", "inválid", "invalid", "resolu", "km_fim não", "ocorrido_em", "formato", "imagem",
                     "informe ", "nenhum dado")


def _codigo_da_excecao(repo: SQLRepository, ev: EventoSync, exc: HTTPException) -> str:
    """Código estável da rejeição (SDD 6.12). Serviços com `ErroRegra` informam o código; os demais são inferidos."""
    codigo = getattr(exc, "codigo", None)
    if codigo:
        return codigo
    detalhe = str(exc.detail).lower()
    if exc.status_code == 403:
        return "OS_REATRIBUIDA"
    if "não é mais executável" in detalhe or "nao e mais executavel" in detalhe:
        return "OS_REATRIBUIDA"
    if (exc.status_code in (400, 409) and ev.tipo != "pausa_registrada" and "pausad" in detalhe
            and visita_service.pausa_ativa(repo, ev.id_visita) is not None):
        return "OS_PAUSADA"
    if exc.status_code == 422:
        return "VALIDACAO"
    if exc.status_code in (400, 404, 413) and any(p in detalhe for p in _PISTAS_VALIDACAO):
        return "VALIDACAO"
    return "TRANSICAO_INVALIDA"


# ---------------------------------------------------------------------------------------------------------------------
# Processamento
# ---------------------------------------------------------------------------------------------------------------------

def _resultado(ev: EventoSync, resultado: str, codigo: Optional[str] = None,
               detalhe: Optional[str] = None) -> ResultadoEvento:
    return ResultadoEvento(client_event_id=ev.client_event_id, resultado=resultado, codigo=codigo, detalhe=detalhe)


def _persistir_rejeicao(repo: SQLRepository, usuario: dict, ev: EventoSync, ocorrido: datetime,
                        payload: Dict[str, Any], id_os: Optional[int], id_visita: Optional[int], codigo: str,
                        detalhe: str, chamado_conflito=None) -> ResultadoEvento:
    """Grava a rejeição (e, no conflito administrativo, a OS -> Pendente) numa transação própria."""
    db = repo.db
    try:
        db.add(SyncEvento(client_event_id=ev.client_event_id, id_tecnico=usuario["user_id"], id_os=id_os,
                          id_visita=id_visita, tipo=ev.tipo, ocorrido_em=ocorrido, payload=cifrar_payload(payload, ev.client_event_id),
                          resultado=REJEITADO, codigo=codigo, detalhe=detalhe))
        if chamado_conflito is not None:
            chamado_service.mover_para_pendente_por_conflito(repo, chamado_conflito, detalhe,
                                                             str(ev.client_event_id))
        db.commit()
    except IntegrityError:  # outro pedido gravou o mesmo client_event_id agora há pouco
        db.rollback()
        existente = db.get(SyncEvento, ev.client_event_id)
        if existente is not None:
            return _resultado(ev, DUPLICADO, existente.codigo, existente.detalhe)
        raise
    except Exception:
        db.rollback()
        raise
    return _resultado(ev, REJEITADO, codigo, detalhe)


def _ocorrido(ev: EventoSync, desvio: timedelta, recebido: datetime):
    """SY-04: corrige o relógio do aparelho quando o desvio passa de 2 min. Devolve (instante, original ou None)."""
    original = ev.ocorrido_em.astimezone(timezone.utc)
    corrigido = original + desvio if abs(desvio) > TOLERANCIA_RELOGIO else original
    if corrigido > recebido:
        corrigido = recebido
    return corrigido, (original if corrigido != original else None)


def _processar_um(repo: SQLRepository, usuario: dict, ev: EventoSync, recebido: datetime, desvio: timedelta,
                  bloqueios: Dict[int, str]) -> ResultadoEvento:
    db = repo.db
    existente = db.get(SyncEvento, ev.client_event_id)
    if existente is not None:
        if existente.id_tecnico != usuario["user_id"]:
            return _resultado(ev, REJEITADO, "VALIDACAO", "client_event_id já utilizado por outro dispositivo.")
        return _resultado(ev, DUPLICADO, existente.codigo, existente.detalhe)

    ocorrido, original = _ocorrido(ev, desvio, recebido)
    payload = dict(ev.payload)
    if original is not None:
        payload["ocorrido_em_original"] = original.isoformat()

    bloqueio = bloqueios.get(ev.id_visita)
    if bloqueio == "transitorio":
        return _resultado(ev, REJEITADO, "ARQUIVO_AUSENTE",
                          "Aguardando o arquivo de um evento anterior desta visita; reenvie na ordem.")
    if bloqueio == "rejeitado":
        return _persistir_rejeicao(repo, usuario, ev, ocorrido, payload, ev.id_os, ev.id_visita,
                                   "DEPENDENCIA_REJEITADA", "Um evento anterior desta visita foi rejeitado.")

    handler = HANDLERS.get(ev.tipo)
    chamado = repo.get_chamado_by_id(ev.id_os)
    visita = repo.get_visita_by_id(ev.id_visita)
    id_os = chamado.id_os if chamado is not None else None
    id_visita = visita.id_visita if visita is not None else None

    def rejeitar(codigo: str, detalhe: str, conflito=None) -> ResultadoEvento:
        return _persistir_rejeicao(repo, usuario, ev, ocorrido, payload, id_os, id_visita, codigo, detalhe, conflito)

    if handler is None:
        return rejeitar("VALIDACAO", f"Tipo de evento desconhecido: '{ev.tipo}'.")
    if chamado is None:
        return rejeitar("VALIDACAO", f"OS {ev.id_os} não encontrada.")
    if chamado.is_cancelled:
        return rejeitar("OS_CANCELADA", "A OS foi cancelada.")
    if chamado.id_tecnico_atribuido != usuario["user_id"]:
        return rejeitar("OS_REATRIBUIDA", "A OS não está mais atribuída a este técnico.")
    if visita is None or visita.id_os != chamado.id_os:
        return rejeitar("VALIDACAO", f"Visita {ev.id_visita} não pertence à OS {ev.id_os}.")

    # Linha de idempotência adicionada ANTES do serviço: o commit do serviço confirma efeito + registro juntos.
    db.add(SyncEvento(client_event_id=ev.client_event_id, id_tecnico=usuario["user_id"], id_os=chamado.id_os,
                      id_visita=visita.id_visita, tipo=ev.tipo, ocorrido_em=ocorrido, payload=cifrar_payload(payload, ev.client_event_id),
                      resultado=APLICADO))
    db.flush()
    ctx = Ctx(repo=repo, usuario=usuario, chamado=chamado, visita=visita, evento=ev, ocorrido=ocorrido, payload=payload)
    try:
        handler(ctx)
        db.commit()  # idempotente: garante a confirmação mesmo se o handler não confirmou
        return _resultado(ev, APLICADO)
    except ArquivoAusente as exc:
        db.rollback()
        bloqueios[ev.id_visita] = "transitorio"
        return _resultado(ev, REJEITADO, "ARQUIVO_AUSENTE", str(exc))
    except ValidationError as exc:
        db.rollback()
        erros = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        return rejeitar("VALIDACAO", f"Payload inválido: {erros}")
    except HTTPException as exc:
        db.rollback()
        codigo = _codigo_da_excecao(repo, ev, exc)
        conflito = None
        if codigo == "OS_PAUSADA" and ev.tipo != "pausa_registrada":
            pausa = visita_service.pausa_ativa(repo, ev.id_visita)
            if pausa is not None and pausa.por_papel == "admin":
                codigo = "CONFLITO_ADMINISTRATIVO"  # SY-05: pausa feita pelo administrador durante o período offline
        if codigo == "CONFLITO_ADMINISTRATIVO":
            conflito = repo.get_chamado_by_id(ev.id_os)
        return rejeitar(codigo, str(exc.detail), conflito)
    except Exception:
        db.rollback()
        raise


def processar_lote(repo: SQLRepository, usuario: dict, lote: LoteSync,
                   recebido_em: Optional[datetime] = None) -> List[ResultadoEvento]:
    """
    Processa o lote por `ocorrido_em` (SY-01) e devolve os resultados NA ORDEM RECEBIDA. Rejeição (ou arquivo ausente) de
    um evento bloqueia os seguintes da MESMA visita neste lote (DEPENDENCIA_REJEITADA / ARQUIVO_AUSENTE).
    """
    recebido = (recebido_em or agora_utc()).astimezone(timezone.utc)
    desvio = recebido - lote.enviado_em.astimezone(timezone.utc)  # SY-04
    ordem = sorted(enumerate(lote.eventos), key=lambda t: (t[1].ocorrido_em.astimezone(timezone.utc), t[0]))
    resultados: Dict[int, ResultadoEvento] = {}
    bloqueios: Dict[int, str] = {}
    for indice, ev in ordem:
        r = _processar_um(repo, usuario, ev, recebido, desvio, bloqueios)
        resultados[indice] = r
        if r.resultado == REJEITADO and r.codigo != "ARQUIVO_AUSENTE":
            bloqueios.setdefault(ev.id_visita, "rejeitado")
        elif r.resultado == REJEITADO and r.codigo == "ARQUIVO_AUSENTE":
            bloqueios.setdefault(ev.id_visita, "transitorio")
    return [resultados[i] for i in range(len(lote.eventos))]


# ---------------------------------------------------------------------------------------------------------------------
# Cache local (GET /api/sync/minhas-os)
# ---------------------------------------------------------------------------------------------------------------------

def minhas_os(repo: SQLRepository, usuario: dict) -> Dict[str, Any]:
    """Todas as OS atribuídas ao técnico e não canceladas, com o estado da visita executável (substitui o cache)."""
    itens = []
    for c in repo.get_chamados(tecnico_id=usuario["user_id"], is_cancelled=False):
        chamado = Chamado.model_validate(c)
        chamado.cliente_nome = c.cliente.razao_social if c.cliente else None
        ultima = repo.get_ultima_visita(c.id_os)
        estado = None
        if ultima is not None and visita_service.visita_vigente(repo, c, ultima):
            estado = visita_service.calcular_estado(repo, c, ultima)
        itens.append({"chamado": chamado, "estado_visita_vigente": estado})
    return {"sincronizado_em": agora_utc(), "os": itens}
