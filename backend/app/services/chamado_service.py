"""
Regras de domínio da OS (SDD seção 5, 6.5, 6.9, 6.10), independentes de HTTP exceto pelas exceções 4xx.

* Validador central de transições (TR-01 / PR-13): QUALQUER mudança de status passa por `validar_transicao`.
  Transição fora da tabela 5.1 -> HTTP 409 com `detail` explicando o status e a ação.
* Criação, atribuição, cancelamento e reagendamento de OS.
* Controle de acesso à OS (SEG-09 / SEG-11): admin vê tudo; técnico só a OS atribuída a ele.
"""
import logging
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, FrozenSet, Optional, Tuple

from fastapi import HTTPException

from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.services import auditoria_service as auditoria
from app.services import equipamento_service
from app.services.tempo import hoje_negocio

logger = logging.getLogger(__name__)

S = StatusChamado


# ---------------------------------------------------------------------------------------------------------------------
# Tabela de transições (SDD 5.1)
# ---------------------------------------------------------------------------------------------------------------------

class AcaoOS(str, Enum):
    CRIAR_SEM_TECNICO = "criar OS sem técnico"
    CRIAR_COM_TECNICO = "criar OS com técnico"
    ATRIBUIR_TECNICO = "atribuir técnico"
    REATRIBUIR_TECNICO = "reatribuir técnico"
    INICIAR_ATENDIMENTO = "iniciar atendimento"
    PAUSAR = "pausar"
    FINALIZAR_VOLTA_SEM_PAUSA = "finalizar deslocamento de volta (sem pausa)"
    FINALIZAR_VOLTA_COM_PAUSA = "finalizar deslocamento de volta (com pausa)"
    REAGENDAR_APOS_PAUSA = "reagendar (OS aguardando reagendamento)"
    REAGENDAR_ANTES_DA_IDA = "reagendar (ida não iniciada)"
    CANCELAR = "cancelar"


# ação -> (status de origem permitidos | None = criação, status de destino | None = mantém o atual)
_TRANSICOES: Dict[AcaoOS, Tuple[Optional[FrozenSet[StatusChamado]], Optional[StatusChamado]]] = {
    AcaoOS.CRIAR_SEM_TECNICO: (None, S.PENDENTE),
    AcaoOS.CRIAR_COM_TECNICO: (None, S.AGENDADO),
    AcaoOS.ATRIBUIR_TECNICO: (frozenset({S.PENDENTE}), S.AGENDADO),
    # Reatribuição: só enquanto não há trabalho em campo em andamento (não consta da 5.1; ver relatório).
    AcaoOS.REATRIBUIR_TECNICO: (frozenset({S.AGENDADO, S.AGUARDANDO_REAGENDAMENTO}), None),
    AcaoOS.INICIAR_ATENDIMENTO: (frozenset({S.AGENDADO}), S.EM_ATENDIMENTO),
    AcaoOS.PAUSAR: (frozenset({S.EM_ATENDIMENTO}), S.PAUSADO),
    AcaoOS.FINALIZAR_VOLTA_SEM_PAUSA: (frozenset({S.EM_ATENDIMENTO}), S.FINALIZADO),
    AcaoOS.FINALIZAR_VOLTA_COM_PAUSA: (frozenset({S.PAUSADO}), S.AGUARDANDO_REAGENDAMENTO),
    AcaoOS.REAGENDAR_APOS_PAUSA: (frozenset({S.AGUARDANDO_REAGENDAMENTO}), S.AGENDADO),
    AcaoOS.REAGENDAR_ANTES_DA_IDA: (frozenset({S.AGENDADO}), S.AGENDADO),
    # Cancelar: tudo menos Finalizado (o cancelamento é flag, o status não muda).
    AcaoOS.CANCELAR: (frozenset({S.PENDENTE, S.AGENDADO, S.EM_ATENDIMENTO, S.PAUSADO, S.AGUARDANDO_REAGENDAMENTO,
                                 S.ABERTO}), None),
}


def _valor(status) -> str:
    return status.value if isinstance(status, Enum) else str(status)


def validar_transicao(status_atual, acao: AcaoOS) -> Optional[StatusChamado]:
    """
    Valida `acao` a partir de `status_atual` (TR-01). Retorna o status de destino (None = permanece).
    Levanta HTTP 409 explicando a transição inválida.
    """
    origens, destino = _TRANSICOES[acao]
    if origens is not None:
        atual = status_atual if isinstance(status_atual, StatusChamado) else StatusChamado(_valor(status_atual))
        if atual not in origens:
            permitidos = ", ".join(sorted(o.value for o in origens))
            raise HTTPException(
                status_code=409,
                detail=(f"Transição inválida: não é possível {acao.value} com a OS em '{atual.value}'. "
                        f"Status permitidos: {permitidos}."))
    return destino


def exigir_status(chamado, permitidos: FrozenSet[StatusChamado], acao: str) -> None:
    """409 quando o status atual da OS não permite uma ação que não muda o status (ex.: iniciar a ida)."""
    atual = chamado.status if isinstance(chamado.status, StatusChamado) else StatusChamado(_valor(chamado.status))
    if atual not in permitidos:
        raise HTTPException(
            status_code=409,
            detail=(f"Transição inválida: não é possível {acao} com a OS em '{atual.value}'. "
                    f"Status permitidos: {', '.join(sorted(p.value for p in permitidos))}."))


# ---------------------------------------------------------------------------------------------------------------------
# Acesso à OS (SEG-09 / SEG-11)
# ---------------------------------------------------------------------------------------------------------------------

def carregar_chamado(repo: SQLRepository, chamado_id: int, usuario: dict, *, permitir_cancelado: bool = False):
    """
    Carrega a OS aplicando a regra de acesso: 404 se não existe (ou cancelada), 403 se o técnico não é o atribuído.
    Admin acessa qualquer OS. Rotas só de técnico já são filtradas por `require_technician_role`.
    """
    chamado = repo.get_chamado_by_id(chamado_id)
    if chamado is None or (chamado.is_cancelled and not permitir_cancelado):
        raise HTTPException(status_code=404, detail="Chamado não encontrado ou cancelado.")
    if usuario.get("role") != "admin" and chamado.id_tecnico_atribuido != usuario.get("user_id"):
        raise HTTPException(status_code=403, detail="Acesso negado a este chamado.")
    return chamado


def carregar_visita(repo: SQLRepository, chamado, visita_id: int):
    """404 se a visita não existe ou não pertence à OS."""
    visita = repo.get_visita_by_id(visita_id)
    if visita is None or visita.id_os != chamado.id_os:
        raise HTTPException(status_code=404, detail=f"Visita com ID {visita_id} não encontrada neste chamado.")
    return visita


# ---------------------------------------------------------------------------------------------------------------------
# Técnico atribuível
# ---------------------------------------------------------------------------------------------------------------------

def _validar_tecnico_atribuivel(repo: SQLRepository, tecnico_id: int):
    tecnico = repo.get_tecnico_by_id(tecnico_id)
    if tecnico is None or not tecnico.is_active:
        raise HTTPException(status_code=404, detail=f"Técnico com id {tecnico_id} não encontrado ou inativo.")
    papel = tecnico.role.value if isinstance(tecnico.role, Enum) else str(tecnico.role)
    if papel != "tecnico":
        raise HTTPException(status_code=400, detail=f"O usuário {tecnico_id} não é um técnico e não pode receber OS.")
    return tecnico


# ---------------------------------------------------------------------------------------------------------------------
# Criar / atualizar
# ---------------------------------------------------------------------------------------------------------------------

def _garantir_visita_aberta(repo: SQLRepository, chamado_id: int, data_agendamento: Optional[date]):
    """
    D1: garante UMA visita aberta executável para a OS que entra em Agendado. data_visita = data_agendamento ou,
    se vazia, hoje (fuso de negócio). Retorna `(visita, criada)`.

    RN-08a (reatribuição após desativação do técnico): se a visita aberta atual NÃO foi iniciada (ida não iniciada),
    ela é reaproveitada. Se a ida já foi iniciada pelo técnico anterior, ela fica como histórico (abandonada) e uma
    visita NOVA, do zero, é criada para o novo técnico.
    """
    visita = repo.get_visita_aberta(chamado_id)
    if visita is not None and not _visita_ida_iniciada(visita):
        if data_agendamento is not None and visita.data_visita != data_agendamento:
            visita.data_visita = data_agendamento
        equipamento_service.garantir_servicos_da_visita(repo, chamado_id, visita)  # v0.5: 1 serviço por equipamento
        return visita, False
    nova = repo.create_visita(chamado_id, {"data_visita": data_agendamento or hoje_negocio()}, commit=False)
    equipamento_service.garantir_servicos_da_visita(repo, chamado_id, nova)
    return nova, True


def criar_chamado(repo: SQLRepository, dados: Dict[str, Any], usuario: dict):
    """RN-10 / T-26: sem técnico -> Pendente; com técnico ativo -> Agendado. Nunca grava Aberto."""
    cliente = repo.get_cliente_by_id(dados["id_cliente"])
    if cliente is None or not cliente.is_active:
        raise HTTPException(status_code=404,
                            detail=f"Cliente com id {dados['id_cliente']} não encontrado ou inativo.")

    dados = dict(dados)
    # O status nunca vem do cliente da API.
    dados.pop("status", None)
    # v0.5 (RN-41 / TR-15): toda OS nasce com ao menos um equipamento (modelo + série); sem isso a OS não é criada.
    equipamentos = dados.pop("equipamentos", None) or []
    if not equipamentos:
        raise HTTPException(status_code=422,
                            detail="A OS precisa ter ao menos um equipamento (modelo + número de série).")
    tecnico_id = dados.get("id_tecnico_atribuido")
    if tecnico_id is not None:
        _validar_tecnico_atribuivel(repo, tecnico_id)
        status = validar_transicao(None, AcaoOS.CRIAR_COM_TECNICO)
    else:
        status = validar_transicao(None, AcaoOS.CRIAR_SEM_TECNICO)

    dados.update({"data_abertura": hoje_negocio(), "is_cancelled": False, "status": status})
    try:
        chamado = repo.create_chamado(dados, commit=False)
        equipamento_service.vincular_na_criacao(repo, chamado.id_os, equipamentos)
        if status == StatusChamado.AGENDADO:
            # D1: toda OS Agendado nasce com exatamente uma visita aberta, na mesma transação.
            _garantir_visita_aberta(repo, chamado.id_os, dados.get("data_agendamento"))
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.OS_CRIADA,
                                 payload={"status": status.value, "id_tecnico": tecnico_id,
                                          "id_cliente": dados["id_cliente"],
                                          "equipamentos": [{"id_equipamento_modelo": e["id_equipamento_modelo"],
                                                            "numero_serie": e["numero_serie"]} for e in equipamentos]})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_chamado_by_id(chamado.id_os)


def atualizar_chamado_admin(repo: SQLRepository, chamado, dados: Dict[str, Any], usuario: dict):
    """
    PATCH administrativo. Regras:
      * `status` nunca é escolhido livremente: Finalizado -> 403; qualquer outro valor diferente do resultado
        implícito da atribuição -> 409 (TR-01).
      * Atribuir técnico ativo a OS Pendente -> Agendado (RN-11 / T-06).
      * Pendente deve ficar sem técnico (TR-08); desatribuir manualmente OS não Pendente -> 409 (a desatribuição
        automática ocorre só na desativação do técnico, RN-08a).
    """
    dados = dict(dados)
    if "is_cancelled" in dados:
        raise HTTPException(status_code=400, detail="Para cancelar a OS use POST /api/chamados/{id}/cancelar.")
    if "data_conclusao" in dados:
        raise HTTPException(status_code=400,
                            detail="data_conclusao é definida pelo sistema ao finalizar o deslocamento de volta.")

    novo_status_pedido = dados.pop("status", None)
    if novo_status_pedido is not None and _valor(novo_status_pedido) == StatusChamado.FINALIZADO.value:
        raise HTTPException(
            status_code=403,
            detail="A OS não pode ser finalizada manualmente: ela é finalizada ao concluir o deslocamento de volta.")

    status_destino: Optional[StatusChamado] = None
    tecnico_anterior = chamado.id_tecnico_atribuido
    atribuiu = False
    if "id_tecnico_atribuido" in dados:
        novo_tecnico = dados["id_tecnico_atribuido"]
        if novo_tecnico is None:
            if _valor(chamado.status) != StatusChamado.PENDENTE.value:
                raise HTTPException(
                    status_code=409,
                    detail=("Transição inválida: não é possível desatribuir manualmente o técnico de uma OS que não "
                            "está 'Pendente'. A desatribuição ocorre automaticamente quando o técnico é desativado "
                            "(RN-08a)."))
            dados.pop("id_tecnico_atribuido")  # Pendente já está sem técnico: nada a fazer
        elif novo_tecnico == tecnico_anterior and _valor(chamado.status) != StatusChamado.PENDENTE.value:
            dados.pop("id_tecnico_atribuido")  # mesmo técnico: sem efeito
        else:
            _validar_tecnico_atribuivel(repo, novo_tecnico)
            if _valor(chamado.status) == StatusChamado.PENDENTE.value:
                status_destino = validar_transicao(chamado.status, AcaoOS.ATRIBUIR_TECNICO)
            else:
                validar_transicao(chamado.status, AcaoOS.REATRIBUIR_TECNICO)
            atribuiu = True

    if novo_status_pedido is not None:
        alvo = status_destino or chamado.status
        if _valor(novo_status_pedido) != _valor(alvo):
            raise HTTPException(
                status_code=409,
                detail=(f"Transição inválida: o status não pode ser alterado por PATCH "
                        f"('{_valor(chamado.status)}' -> '{_valor(novo_status_pedido)}'). "
                        f"Use as ações do fluxo (atribuir, iniciar, pausar, reagendar, cancelar)."))

    if "id_cliente" in dados:
        cliente = repo.get_cliente_by_id(dados["id_cliente"])
        if cliente is None or not cliente.is_active:
            raise HTTPException(status_code=404,
                                detail=f"Cliente com id {dados['id_cliente']} não encontrado ou inativo.")

    if not dados and status_destino is None:
        return chamado  # nada efetivamente alterado (ex.: status igual ao atual)

    if status_destino == StatusChamado.AGENDADO:  # Pendente -> Agendado exige equipamento (TR-15 / RN-46)
        equipamento_service.exigir_com_equipamento(repo, chamado)

    if status_destino is not None:
        dados["status"] = status_destino
    try:
        chamado_db = repo.update_chamado(chamado.id_os, dados, commit=False)
        if status_destino == StatusChamado.AGENDADO:  # Pendente -> Agendado: D1
            visita, _ = _garantir_visita_aberta(repo, chamado.id_os, chamado_db.data_agendamento)
            if chamado_db.data_agendamento is None:
                chamado_db.data_agendamento = visita.data_visita
        auditoria.registrar_acao(
            repo.db, id_os=chamado.id_os, usuario=usuario,
            acao=auditoria.OS_ATRIBUIDA if atribuiu else auditoria.OS_ATUALIZADA,
            payload={"campos": sorted(k for k in dados if k != "status"),
                     "id_tecnico": dados.get("id_tecnico_atribuido"), "id_tecnico_anterior": tecnico_anterior,
                     "status": _valor(status_destino) if status_destino else None})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_chamado_by_id(chamado.id_os)


# ---------------------------------------------------------------------------------------------------------------------
# Cancelar (6.9)
# ---------------------------------------------------------------------------------------------------------------------

def cancelar_chamado(repo: SQLRepository, chamado, motivo: str, usuario: dict):
    """
    Cancela a OS (RF-11 / RN-12): is_cancelled + motivo + data + autor, e encerra as pausas ativas, tudo na
    MESMA transação. Finalizado ou já cancelada -> 409. Visitas, fotos e serviços são mantidos.
    """
    agora = datetime.now(timezone.utc)
    try:
        # D11: trava a linha e relê o estado atual (outro pedido pode ter finalizado/cancelado a OS agora há pouco).
        chamado = repo.lock_chamado(chamado.id_os) or chamado
        if chamado.is_cancelled:
            raise HTTPException(status_code=409, detail="OS já está cancelada.")
        validar_transicao(chamado.status, AcaoOS.CANCELAR)  # 409 para Finalizado

        pausas_encerradas = repo.resolve_pausas_for_chamado(chamado.id_os, quando=agora)
        repo.update_chamado(chamado.id_os, {
            "is_cancelled": True,
            "motivo_cancelamento": motivo,
            "cancelado_em": agora,
            "cancelado_por": usuario.get("user_id"),
        }, commit=False)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.OS_CANCELADA,
                                 payload={"motivo": motivo, "status_anterior": _valor(chamado.status),
                                          "pausas_encerradas": pausas_encerradas})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_chamado_by_id(chamado.id_os)


# ---------------------------------------------------------------------------------------------------------------------
# Reagendar (6.10)
# ---------------------------------------------------------------------------------------------------------------------

_DICA_REAGENDAR = {
    StatusChamado.PENDENTE.value: "Atribua um técnico primeiro.",
    StatusChamado.EM_ATENDIMENTO.value: "A OS deve ser pausada e o deslocamento de volta finalizado.",
    StatusChamado.PAUSADO.value: "O técnico deve finalizar o deslocamento de volta primeiro.",
    StatusChamado.FINALIZADO.value: "OS finalizada é estado terminal.",
}


def _visita_ida_iniciada(visita) -> bool:
    return bool(getattr(visita, "ida_inicio_em", None) or (getattr(visita, "hora_inicio_ida", None) or "").strip())


def reagendar_chamado(repo: SQLRepository, chamado, data_visita: date, usuario: dict):
    """
    Retorna `(visita, criada)`.

      Aguardando Reagendamento -> cria NOVA visita, encerra as pausas, OS Agendado + data_agendamento. (criada=True)
      Agendado com ida não iniciada -> ALTERA a data da visita aberta (não cria visita vazia). (criada=False)
      Agendado SEM visita aberta (legado) -> cria a visita. (criada=True)
      Qualquer outro status (Pendente, Em Atendimento, Pausado, Finalizado, ida iniciada) -> 409 com o status.

    Recusa data passada (422, fuso de negócio) e exige técnico atribuído ativo (409).
    """
    status = _valor(chamado.status)
    if data_visita < hoje_negocio():
        raise HTTPException(status_code=422, detail="A data do reagendamento não pode estar no passado.")
    if status in (StatusChamado.AGUARDANDO_REAGENDAMENTO.value, StatusChamado.AGENDADO.value):
        tecnico = repo.get_tecnico_by_id(chamado.id_tecnico_atribuido) if chamado.id_tecnico_atribuido else None
        if tecnico is None or not tecnico.is_active:
            raise HTTPException(
                status_code=409,
                detail="O técnico atribuído está inativo ou ausente; atribua um técnico ativo antes de reagendar.")
        equipamento_service.exigir_com_equipamento(repo, chamado)  # TR-15: OS legada sem equipamento -> 409
    try:
        if status == StatusChamado.AGUARDANDO_REAGENDAMENTO.value:
            validar_transicao(chamado.status, AcaoOS.REAGENDAR_APOS_PAUSA)
            agora = datetime.now(timezone.utc)
            visita = repo.create_visita(chamado.id_os, {"data_visita": data_visita}, commit=False)
            equipamento_service.garantir_servicos_da_visita(repo, chamado.id_os, visita)
            pausas_encerradas = repo.resolve_pausas_for_chamado(chamado.id_os, quando=agora)
            repo.update_chamado(chamado.id_os, {"status": StatusChamado.AGENDADO, "data_agendamento": data_visita,
                                                "data_conclusao": None}, commit=False)
            criada = True
            payload = {"data_visita": data_visita.isoformat(), "visita": "nova",
                       "pausas_encerradas": pausas_encerradas}
        elif status == StatusChamado.AGENDADO.value:
            validar_transicao(chamado.status, AcaoOS.REAGENDAR_ANTES_DA_IDA)
            visita = repo.get_visita_aberta(chamado.id_os)
            if visita is None:
                visita = repo.create_visita(chamado.id_os, {"data_visita": data_visita}, commit=False)
                equipamento_service.garantir_servicos_da_visita(repo, chamado.id_os, visita)
                criada = True
                payload = {"data_visita": data_visita.isoformat(), "visita": "nova (OS sem visita aberta)"}
            else:
                if _visita_ida_iniciada(visita):
                    raise HTTPException(
                        status_code=409,
                        detail="Transição inválida: o técnico já iniciou o deslocamento de ida; a OS 'Agendado' "
                               "não pode ser reagendada.")
                visita.data_visita = data_visita
                criada = False
                payload = {"data_visita": data_visita.isoformat(), "visita": "existente",
                           "id_visita": visita.id_visita}
            repo.update_chamado(chamado.id_os, {"data_agendamento": data_visita}, commit=False)
        else:
            # Pendente, Em Atendimento, Pausado, Finalizado (cancelada já foi barrada com 404): tabela 6.10.
            raise HTTPException(status_code=409, detail=(
                f"Transição inválida: não é possível reagendar com a OS em '{status}'. "
                f"{_DICA_REAGENDAR.get(status, '')}").strip())

        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.OS_REAGENDADA,
                                 payload=payload)
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_visita_by_id(visita.id_visita), criada


# ---------------------------------------------------------------------------------------------------------------------
# SY-05: conflito administrativo na sincronização offline
# ---------------------------------------------------------------------------------------------------------------------

def mover_para_pendente_por_conflito(repo: SQLRepository, chamado, motivo: str, id_evento: str) -> bool:
    """
    SY-05 / PRD RN-38: ação offline incompatível com alteração administrativa. A OS NÃO finalizada e NÃO cancelada
    passa a `Pendente`, sem técnico, e as pausas ativas são encerradas; visitas, fotos e serviços ficam como histórico.
    Cancelamento e finalização já efetivados não são revertidos (devolve False). Sem commit: entra na transação do
    evento rejeitado. A auditoria usa o ator `sistema`.
    """
    atual = repo.get_chamado_by_id(chamado.id_os)
    if atual is None or atual.is_cancelled or _valor(atual.status) == StatusChamado.FINALIZADO.value:
        return False
    tecnico_anterior = atual.id_tecnico_atribuido
    status_anterior = _valor(atual.status)
    pausas = repo.resolve_pausas_for_chamado(atual.id_os, quando=datetime.now(timezone.utc))
    repo.update_chamado(atual.id_os, {"id_tecnico_atribuido": None, "status": StatusChamado.PENDENTE,
                                      "data_conclusao": None}, commit=False)
    auditoria.registrar_acao(repo.db, id_os=atual.id_os, usuario=None, acao=auditoria.CONFLITO_ADMINISTRATIVO,
                             payload={"motivo": motivo, "id_evento": id_evento, "id_tecnico_anterior": tecnico_anterior,
                                      "status_anterior": status_anterior, "pausas_encerradas": pausas})
    return True


# ---------------------------------------------------------------------------------------------------------------------
# RN-08a: desativação de técnico
# ---------------------------------------------------------------------------------------------------------------------

def desatribuir_os_do_tecnico(db, tecnico_id: int, usuario: dict) -> list:
    """
    Regra aprovada (RN-08a): ao desativar um técnico, TODAS as OS dele não finalizadas e não canceladas voltam a
    `Pendente` sem técnico (qualquer status: Agendado, Em Atendimento, Pausado, Aguardando Reagendamento), na mesma
    transação da desativação (quem chama confirma o commit). Retorna os ids das OS afetadas.

    Decisões registradas:
      * Visitas, serviços, fotos, comprovantes e pausas são PRESERVADOS (histórico). A visita aberta fica
        "abandonada": só a visita mais recente de uma OS é executável (ver SQLRepository.get_visita_aberta).
      * Pausas ativas são ENCERRADAS (is_ativa=false, encerrada_em): o ciclo Pausado -> reagendamento deixa de
        existir quando a OS volta a Pendente e uma pausa "ativa" numa OS sem técnico quebraria a integridade
        (Pendente sem pausa pendente). O registro continua visível no histórico.
      * OS Finalizadas e canceladas não mudam. Admin não recebe OS, logo desativar admin não desatribui nada.
      * Auditoria: uma linha DESATRIBUIDA_POR_DESATIVACAO (papel do ator, admin) por OS, com todos os ids no payload.
    """
    repo = SQLRepository(db)
    tecnico = repo.get_tecnico_by_id(tecnico_id)
    papel = tecnico.role.value if tecnico is not None and isinstance(tecnico.role, Enum) else getattr(tecnico, "role", None)
    if tecnico is None or papel != "tecnico":
        return []
    from sqlalchemy import select
    from app.models.chamado import OrdemServico
    afetadas = db.execute(
        select(OrdemServico)
        .where(OrdemServico.id_tecnico_atribuido == tecnico_id,
               OrdemServico.is_cancelled.is_(False),
               OrdemServico.status != StatusChamado.FINALIZADO)
        .with_for_update().execution_options(populate_existing=True)
    ).scalars().all()
    if not afetadas:
        return []

    ids = sorted(os_.id_os for os_ in afetadas)
    agora = datetime.now(timezone.utc)
    for os_ in afetadas:
        status_anterior = _valor(os_.status)
        pausas = repo.resolve_pausas_for_chamado(os_.id_os, quando=agora)
        os_.id_tecnico_atribuido = None
        os_.status = StatusChamado.PENDENTE
        os_.data_conclusao = None
        auditoria.registrar_acao(
            db, id_os=os_.id_os, usuario=usuario, acao=auditoria.DESATRIBUIDA_POR_DESATIVACAO,
            payload={"id_tecnico": tecnico_id, "status_anterior": status_anterior, "pausas_encerradas": pausas,
                     "ids_os": ids})
    db.flush()
    return ids
