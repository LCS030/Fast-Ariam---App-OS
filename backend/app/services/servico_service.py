"""
Registro de serviço por equipamento (SDD 6.7, 6.13; PRD RN-42, RN-47, RN-49).

* Técnico: preenche defeitos/materiais do registro criado pelo servidor e aciona "Salvar conserto".
* Administrador, SOMENTE com a OS `Finalizado` (não cancelada): corrige fotos comprobatórias e materiais. A correção de
  materiais RECALCULA o custo reutilizando os valores congelados na finalização (RN-33 / RN-49). Tudo é auditado.
* Nada aqui altera modelo, série, defeitos, conserto salvo, assinatura, km, horários nem o status da OS.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.services import auditoria_service as auditoria
from app.services import custo_service, visita_service

logger = logging.getLogger(__name__)


def _materiais(servico) -> List[Dict[str, Any]]:
    return [{"nome": m.nome, "quantidade": m.quantidade, "valor": float(m.valor)} for m in servico.materiais_utilizados]


def _status(chamado) -> str:
    return chamado.status.value if hasattr(chamado.status, "value") else str(chamado.status)


# ---------------------------------------------------------------------------------------------------------------------
# Técnico
# ---------------------------------------------------------------------------------------------------------------------

def atualizar_servico_tecnico(repo: SQLRepository, chamado, visita, servico, dados: Dict[str, Any], usuario: dict):
    """
    PATCH .../servicos/{s} pelo técnico: defeitos, descrições e materiais do equipamento. Aceito com a visita vigente
    e o atendimento ainda não finalizado (inclusive ANTES de iniciar). Equipamento/série nunca são editáveis (o schema
    já responde 422). Não deixa o conserto salvo sem defeito principal.
    """
    if _status(chamado) == StatusChamado.FINALIZADO.value:
        raise HTTPException(status_code=409,
                            detail="OS 'Finalizado' não aceita alterações do técnico; peça a correção ao escritório.")
    visita_service.exigir_visita_vigente(repo, chamado, visita)
    if visita_service.marco(visita, "atendimento_fim") is not None:
        raise HTTPException(status_code=409,
                            detail="O atendimento já foi finalizado; o serviço não pode mais ser alterado.")
    if (servico.conserto_salvo_em is not None and "defeitos_principais" in dados
            and not (dados["defeitos_principais"] or [])):
        raise HTTPException(status_code=422,
                            detail="O conserto já foi salvo: mantenha ao menos um defeito principal.")
    try:
        repo.update_servico_equipamento(servico.id_servico, dados, commit=False)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.SERVICO_ATUALIZADO,
                                 payload={"id_visita": visita.id_visita, "id_servico": servico.id_servico,
                                          "id_os_equipamento": servico.id_os_equipamento,
                                          "campos": sorted(dados)})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_servico_by_id(servico.id_servico)


def salvar_conserto(repo: SQLRepository, chamado, visita, servico, ocorrido_em: Optional[datetime], usuario: dict):
    """
    RN-47: marca o conserto do equipamento como salvo. Exige atendimento iniciado, não finalizado e sem pausa ativa
    (400) e ao menos um defeito principal (422). Idempotente: repetir mantém a primeira marca.
    """
    if _status(chamado) == StatusChamado.FINALIZADO.value:
        raise HTTPException(status_code=409, detail="OS 'Finalizado' não aceita novos registros de conserto.")
    visita_service.exigir_visita_vigente(repo, chamado, visita)
    if visita_service.pausa_ativa(repo, visita.id_visita) is not None:
        raise HTTPException(status_code=400,
                            detail="Não é possível salvar o conserto enquanto a OS estiver pausada.")
    if visita_service.marco(visita, "atendimento_inicio") is None:
        raise HTTPException(status_code=400, detail="O atendimento ainda não foi iniciado.")
    if visita_service.marco(visita, "atendimento_fim") is not None:
        raise HTTPException(status_code=400, detail="O atendimento já foi finalizado.")
    if not servico.defeitos_principais:
        raise HTTPException(status_code=422,
                            detail="Informe ao menos um defeito principal antes de salvar o conserto.")
    if servico.conserto_salvo_em is not None:
        return servico  # idempotente
    momento, _ = visita_service._momento(ocorrido_em)
    try:
        servico.conserto_salvo_em = momento
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.CONSERTO_SALVO,
                                 payload={"id_visita": visita.id_visita, "id_servico": servico.id_servico,
                                          "id_os_equipamento": servico.id_os_equipamento})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_servico_by_id(servico.id_servico)


def exigir_fase_da_foto(chamado, visita, tipo: str) -> None:
    """
    PR-42: a foto de defeito vale antes de iniciar (OS Agendado) ou em atendimento; a de conserto só em atendimento.
    Nenhuma foto de serviço do técnico depois de finalizado o atendimento.
    """
    status = _status(chamado)
    if visita_service.marco(visita, "atendimento_fim") is not None:
        raise HTTPException(status_code=409,
                            detail="O atendimento já foi finalizado; novas fotos de serviço não são aceitas.")
    if tipo == "defeito" and status not in (StatusChamado.AGENDADO.value, StatusChamado.EM_ATENDIMENTO.value):
        raise HTTPException(
            status_code=409,
            detail=f"A foto do defeito só pode ser registrada com a OS 'Agendado' ou 'Em Atendimento' (atual: '{status}').")
    if tipo == "conserto" and status != StatusChamado.EM_ATENDIMENTO.value:
        raise HTTPException(
            status_code=409,
            detail=("A foto do conserto só pode ser registrada depois de iniciar o atendimento e sem pausa "
                    f"(status atual: '{status}')."))


# ---------------------------------------------------------------------------------------------------------------------
# Administrador: correção pós-finalização (RN-49)
# ---------------------------------------------------------------------------------------------------------------------

def exigir_correcao_admin(chamado) -> None:
    """A correção administrativa só vale com a OS Finalizada e não cancelada; em qualquer outro caso 409."""
    if chamado.is_cancelled:
        raise HTTPException(status_code=409, detail="OS cancelada: não há correção administrativa.")
    if _status(chamado) != StatusChamado.FINALIZADO.value:
        raise HTTPException(
            status_code=409,
            detail=("A correção administrativa de fotos e materiais só é permitida com a OS 'Finalizado' "
                    f"(status atual: '{_status(chamado)}')."))


def registrar_foto_corrigida(repo: SQLRepository, chamado, visita, servico, foto, acao: str, usuario: dict) -> None:
    """Auditoria da foto enviada/removida pelo admin (sem commit)."""
    auditoria.registrar_acao(
        repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.FOTO_CORRIGIDA_ADMIN,
        payload={"acao": acao, "id_visita": visita.id_visita, "id_servico": servico.id_servico,
                 "id_os_equipamento": servico.id_os_equipamento, "id_foto": getattr(foto, "id_foto", None),
                 "tipo": foto.tipo, "url": foto.url})


def contar_fotos(servico, tipo: str) -> int:
    return sum(1 for f in servico.fotos if f.tipo == tipo)


def remover_foto_admin(repo: SQLRepository, chamado, visita, servico, foto_id: int, usuario: dict) -> None:
    """DELETE .../fotos/{id}: nunca remove a ÚLTIMA foto do tipo do equipamento (troque enviando a nova antes)."""
    exigir_correcao_admin(chamado)
    foto = repo.get_foto_servico(foto_id)
    if foto is None or foto.id_servico != servico.id_servico:
        raise HTTPException(status_code=404, detail="Foto não encontrada neste serviço.")
    if contar_fotos(servico, foto.tipo) <= 1:
        raise HTTPException(
            status_code=409,
            detail=(f"Esta é a única foto de {foto.tipo} do equipamento e não pode ser removida: envie a foto "
                    "substituta primeiro e depois remova a antiga."))
    try:
        registrar_foto_corrigida(repo, chamado, visita, servico, foto, "removida", usuario)
        repo.delete_foto_servico(foto, commit=False)
        repo.commit()
    except Exception:
        repo.rollback()
        raise


def corrigir_materiais_admin(repo: SQLRepository, chamado, visita, servico, materiais: List[Dict[str, Any]],
                             usuario: dict):
    """
    PATCH .../servicos/{s} pelo admin em OS Finalizada: SOMENTE `materiais_utilizados`. Recalcula o custo da OS com os
    valores congelados na finalização e registra total anterior/novo em `log_acao`.
    """
    exigir_correcao_admin(chamado)
    antes = _materiais(servico)
    try:
        repo.update_servico_equipamento(servico.id_servico, {"materiais_utilizados": materiais}, commit=False)
        repo.flush()
        repo.db.refresh(chamado)  # a árvore da OS reflete os materiais corrigidos no cálculo
        anterior, custo = custo_service.recalcular_custo_finalizado(repo.db, chamado)
        repo.db.refresh(servico)
        auditoria.registrar_acao(
            repo.db, id_os=chamado.id_os, usuario=usuario, acao=auditoria.MATERIAIS_CORRIGIDOS_ADMIN,
            payload={"id_visita": visita.id_visita, "id_servico": servico.id_servico,
                     "id_os_equipamento": servico.id_os_equipamento,
                     "materiais_antes": antes, "materiais_depois": _materiais(servico),
                     "custo_total_anterior": anterior, "custo_total_novo": custo.total_geral})
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return repo.get_servico_by_id(servico.id_servico)
