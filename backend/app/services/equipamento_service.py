"""
Catálogo de modelos e equipamentos da OS (SDD 4.8, 5.3 TR-12/TR-13/TR-15, 6.13; PRD 6.10, RN-40..RN-49).

* O técnico NÃO cadastra nem edita equipamento (RN-42): catálogo e vínculo são do administrador.
* Toda OS tem ao menos um equipamento (RN-41 / TR-15).
* O servidor cria UM registro `servico_equipamento` por equipamento da OS em cada visita aberta; o técnico só o
  preenche (defeitos, materiais, fotos, "Salvar conserto").
* Pré-condições (validadas aqui, dentro da transação de quem chama; AR-09):
    - iniciar atendimento: ≥ 1 foto de defeito por equipamento da OS na visita (TR-12 / RN-43);
    - finalizar atendimento: conserto salvo + ≥ 1 foto de conserto por equipamento na visita (TR-13 / RN-44).
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.erros import ErroRegra
from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.services import auditoria_service as auditoria

logger = logging.getLogger(__name__)

MSG_OS_SEM_EQUIPAMENTO = ("OS sem equipamento vinculado: o administrador precisa vincular ao menos um equipamento "
                          "(modelo + número de série) à OS.")


def _status(chamado) -> str:
    return chamado.status.value if hasattr(chamado.status, "value") else str(chamado.status)


def descrever(equipamento) -> str:
    """Texto curto para mensagens: 'Freezer vertical modelo X (série FZ-1)'."""
    return f"{equipamento.modelo} (série {equipamento.numero_serie})"


# ---------------------------------------------------------------------------------------------------------------------
# Catálogo de modelos (admin)
# ---------------------------------------------------------------------------------------------------------------------

def criar_modelo(repo: SQLRepository, nome: str, usuario: dict):
    """RN-40: nome único sem diferenciar maiúsculas e sem espaços nas pontas -> 409 se já existir."""
    nome = nome.strip()
    if repo.get_modelo_por_nome(nome) is not None:
        raise HTTPException(status_code=409, detail=f"Já existe um modelo de equipamento chamado '{nome}'.")
    try:
        modelo = repo.create_modelo(nome, commit=False)
        auditoria.registrar_acao(repo.db, id_os=None, usuario=usuario, acao=auditoria.EQUIPAMENTO_MODELO_CRIADO,
                                 payload={"id_equipamento_modelo": modelo.id_equipamento_modelo, "modelo": nome})
        repo.commit()
    except IntegrityError:
        repo.rollback()
        raise HTTPException(status_code=409, detail=f"Já existe um modelo de equipamento chamado '{nome}'.")
    except Exception:
        repo.rollback()
        raise
    return repo.get_modelo_by_id(modelo.id_equipamento_modelo)


def atualizar_modelo(repo: SQLRepository, modelo_id: int, dados: Dict[str, Any], usuario: dict):
    """Renomear (reescreve o histórico exibido, PR-45) e/ou ativar/desativar. Nunca exclui."""
    modelo = repo.get_modelo_by_id(modelo_id)
    if modelo is None:
        raise HTTPException(status_code=404, detail=f"Modelo de equipamento {modelo_id} não encontrado.")
    antes = {"modelo": modelo.modelo, "is_active": bool(modelo.is_active)}
    novo_nome = dados.get("modelo")
    if novo_nome is not None:
        novo_nome = novo_nome.strip()
        existente = repo.get_modelo_por_nome(novo_nome)
        if existente is not None and existente.id_equipamento_modelo != modelo.id_equipamento_modelo:
            raise HTTPException(status_code=409, detail=f"Já existe um modelo de equipamento chamado '{novo_nome}'.")
    try:
        if novo_nome is not None:
            modelo.modelo = novo_nome
        if dados.get("is_active") is not None:
            modelo.is_active = bool(dados["is_active"])
        desativou = antes["is_active"] and not modelo.is_active
        acao = auditoria.EQUIPAMENTO_MODELO_DESATIVADO if desativou else auditoria.EQUIPAMENTO_MODELO_ATUALIZADO
        auditoria.registrar_acao(repo.db, id_os=None, usuario=usuario, acao=acao,
                                 payload={"id_equipamento_modelo": modelo.id_equipamento_modelo, "antes": antes,
                                          "depois": {"modelo": modelo.modelo, "is_active": bool(modelo.is_active)}})
        repo.commit()
    except IntegrityError:
        repo.rollback()
        raise HTTPException(status_code=409, detail=f"Já existe um modelo de equipamento chamado '{novo_nome}'.")
    except Exception:
        repo.rollback()
        raise
    return repo.get_modelo_by_id(modelo_id)


# ---------------------------------------------------------------------------------------------------------------------
# Equipamentos da OS (admin escreve; técnico atribuído só lê)
# ---------------------------------------------------------------------------------------------------------------------

def _modelo_vinculavel(repo: SQLRepository, modelo_id: int, *, na_criacao: bool):
    """Modelo existente e ATIVO. Inexistente: 422 na criação da OS (corpo inválido), 404 no sub-recurso."""
    modelo = repo.get_modelo_by_id(modelo_id)
    if modelo is None:
        raise HTTPException(status_code=422 if na_criacao else 404,
                            detail=f"Modelo de equipamento {modelo_id} não encontrado.")
    if not modelo.is_active:
        raise HTTPException(status_code=422,
                            detail=f"O modelo '{modelo.modelo}' está desativado e não pode ser vinculado a uma OS.")
    return modelo


def vincular_na_criacao(repo: SQLRepository, chamado_id: int, itens: List[Dict[str, Any]]) -> list:
    """Vínculos da OS recém-criada (mesma transação; quem chama confirma). Lista vazia -> 422 (RN-41)."""
    if not itens:
        raise HTTPException(status_code=422, detail="A OS precisa ter ao menos um equipamento (modelo + número de série).")
    vistos = set()
    criados = []
    for item in itens:
        serie = str(item["numero_serie"]).strip()
        if serie.upper() in vistos:
            raise HTTPException(status_code=422, detail=f"Número de série repetido na lista de equipamentos: '{serie}'.")
        vistos.add(serie.upper())
        _modelo_vinculavel(repo, item["id_equipamento_modelo"], na_criacao=True)
        criados.append(repo.add_os_equipamento(chamado_id, item["id_equipamento_modelo"], serie, commit=False))
    return criados


def exigir_com_equipamento(repo: SQLRepository, chamado) -> None:
    """TR-15 / RN-46: OS legada sem equipamento não pode ser atribuída, reagendada nem iniciada (409)."""
    if not repo.get_os_equipamentos(chamado.id_os):
        raise HTTPException(status_code=409, detail=MSG_OS_SEM_EQUIPAMENTO)


def _atendimento_iniciado(visita) -> bool:
    return bool(getattr(visita, "atendimento_inicio_em", None)
                or (getattr(visita, "hora_inicio_atendimento", None) or "").strip())


def _exigir_edicao_permitida(repo: SQLRepository, chamado) -> None:
    """RN-45: OS não Finalizada/cancelada e atendimento da visita vigente ainda NÃO iniciado (senão 409)."""
    if chamado.is_cancelled:
        raise HTTPException(status_code=409, detail="OS cancelada: os equipamentos não podem ser alterados.")
    if _status(chamado) == StatusChamado.FINALIZADO.value:
        raise HTTPException(
            status_code=409,
            detail=("OS 'Finalizado': modelo e número de série não podem ser alterados. "
                    "Só fotos e materiais são corrigíveis (RN-49)."))
    visita = repo.get_visita_aberta(chamado.id_os)
    if visita is not None and _atendimento_iniciado(visita):
        raise HTTPException(
            status_code=409,
            detail=("O atendimento desta OS já foi iniciado: os equipamentos não podem mais ser alterados "
                    "(RN-45). A edição só volta com a OS Finalizada, e apenas para fotos e materiais."))


def _servico_tem_conteudo(servico) -> bool:
    return bool(servico.fotos or servico.defeitos or servico.materiais_utilizados or servico.conserto_salvo_em
                or servico.defeito_outros_descricao or servico.vazamento_ponto_descricao)


def garantir_servicos_da_visita(repo: SQLRepository, chamado_id: int, visita) -> list:
    """
    Cria o registro de serviço que falte para cada equipamento da OS na visita (um por equipamento). Idempotente;
    sem commit (entra na transação de quem chama). OS legada sem equipamento não gera registros.
    """
    equipamentos = repo.get_os_equipamentos(chamado_id)
    if not equipamentos:
        return []
    existentes = {s.id_os_equipamento for s in repo.get_servicos_by_visita(visita.id_visita)}
    criados = []
    for equipamento in equipamentos:
        if equipamento.id_os_equipamento not in existentes:
            criados.append(repo.create_servico_equipamento(
                visita.id_visita, {"id_os_equipamento": equipamento.id_os_equipamento, "is_legado": False},
                commit=False))
    return criados


def _garantir_na_visita_aberta(repo: SQLRepository, chamado) -> None:
    visita = repo.get_visita_aberta(chamado.id_os)
    if visita is not None and _status(chamado) != StatusChamado.PENDENTE.value:
        garantir_servicos_da_visita(repo, chamado.id_os, visita)


def _payload_equipamento(equipamento) -> Dict[str, Any]:
    return {"id_os_equipamento": equipamento.id_os_equipamento,
            "id_equipamento_modelo": equipamento.id_equipamento_modelo, "numero_serie": equipamento.numero_serie}


def vincular(repo: SQLRepository, chamado, modelo_id: int, numero_serie: str, usuario: dict):
    """POST /chamados/{id}/equipamentos (admin)."""
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    _exigir_edicao_permitida(repo, chamado)
    _modelo_vinculavel(repo, modelo_id, na_criacao=False)
    serie = numero_serie.strip()
    if repo.get_os_equipamento_por_serie(chamado.id_os, serie) is not None:
        raise HTTPException(status_code=409, detail=f"O número de série '{serie}' já está vinculado a esta OS.")
    try:
        equipamento = repo.add_os_equipamento(chamado.id_os, modelo_id, serie, commit=False)
        _garantir_na_visita_aberta(repo, chamado)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                 acao=auditoria.OS_EQUIPAMENTO_VINCULADO, payload=_payload_equipamento(equipamento))
        repo.commit()
    except IntegrityError:
        repo.rollback()
        raise HTTPException(status_code=409, detail=f"O número de série '{serie}' já está vinculado a esta OS.")
    except Exception:
        repo.rollback()
        raise
    return repo.get_os_equipamento(equipamento.id_os_equipamento)


def _carregar_equipamento_da_os(repo: SQLRepository, chamado, os_equipamento_id: int):
    equipamento = repo.get_os_equipamento(os_equipamento_id)
    if equipamento is None or equipamento.id_os != chamado.id_os:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado nesta OS.")
    return equipamento


def atualizar_vinculo(repo: SQLRepository, chamado, os_equipamento_id: int, dados: Dict[str, Any], usuario: dict):
    """PATCH /chamados/{id}/equipamentos/{eq} (admin): corrigir modelo e/ou série até o início do atendimento."""
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    _exigir_edicao_permitida(repo, chamado)
    equipamento = _carregar_equipamento_da_os(repo, chamado, os_equipamento_id)
    antes = _payload_equipamento(equipamento)
    if dados.get("id_equipamento_modelo") is not None and dados["id_equipamento_modelo"] != equipamento.id_equipamento_modelo:
        _modelo_vinculavel(repo, dados["id_equipamento_modelo"], na_criacao=False)
    serie = dados.get("numero_serie")
    if serie is not None:
        serie = serie.strip()
        existente = repo.get_os_equipamento_por_serie(chamado.id_os, serie)
        if existente is not None and existente.id_os_equipamento != equipamento.id_os_equipamento:
            raise HTTPException(status_code=409, detail=f"O número de série '{serie}' já está vinculado a esta OS.")
    try:
        if dados.get("id_equipamento_modelo") is not None:
            equipamento.id_equipamento_modelo = dados["id_equipamento_modelo"]
        if serie is not None:
            equipamento.numero_serie = serie
        repo.flush()
        repo.db.refresh(equipamento)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                 acao=auditoria.OS_EQUIPAMENTO_ALTERADO,
                                 payload={"antes": antes, "depois": _payload_equipamento(equipamento)})
        repo.commit()
    except IntegrityError:
        repo.rollback()
        raise HTTPException(status_code=409, detail=f"O número de série '{serie}' já está vinculado a esta OS.")
    except Exception:
        repo.rollback()
        raise
    return repo.get_os_equipamento(os_equipamento_id)


def remover_vinculo(repo: SQLRepository, chamado, os_equipamento_id: int, usuario: dict) -> None:
    """
    DELETE /chamados/{id}/equipamentos/{eq} (admin). 409 se for o último, se houver conteúdo registrado (foto, defeito,
    material, conserto) em qualquer visita ou depois do início do atendimento. Registros de serviço VAZIOS (criados
    automaticamente) são removidos na mesma transação.
    """
    chamado = repo.lock_chamado(chamado.id_os) or chamado
    _exigir_edicao_permitida(repo, chamado)
    equipamento = _carregar_equipamento_da_os(repo, chamado, os_equipamento_id)
    if len(repo.get_os_equipamentos(chamado.id_os)) <= 1:
        raise HTTPException(status_code=409, detail="Não é possível remover o último equipamento: a OS precisa ter ao menos um.")
    servicos = repo.get_servicos_do_equipamento(os_equipamento_id)
    if any(_servico_tem_conteudo(s) for s in servicos):
        raise HTTPException(
            status_code=409,
            detail=("Este equipamento já tem fotos, defeitos, materiais ou conserto registrados e não pode ser removido."))
    payload = _payload_equipamento(equipamento)
    try:
        for servico in servicos:
            repo.delete_servico(servico, commit=False)
        repo.flush()
        repo.delete_os_equipamento(equipamento, commit=False)
        auditoria.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                 acao=auditoria.OS_EQUIPAMENTO_REMOVIDO, payload=payload)
        repo.commit()
    except Exception:
        repo.rollback()
        raise


# ---------------------------------------------------------------------------------------------------------------------
# Pendências por visita (TR-12 / TR-13) e estado
# ---------------------------------------------------------------------------------------------------------------------

def avaliar_visita(repo: SQLRepository, chamado, visita) -> Dict[str, Any]:
    """
    Situação de cada equipamento da OS na visita. `atualizar=True` relê do banco (nada de cache da sessão).

    Retorna `{"sem_equipamento", "equipamentos": [...], "pendentes_defeito": [...], "pendentes_conserto": [...]}`.
    """
    equipamentos = repo.get_os_equipamentos(chamado.id_os)
    servicos = {s.id_os_equipamento: s for s in repo.get_servicos_by_visita(visita.id_visita, atualizar=True)
                if s.id_os_equipamento is not None}
    itens = []
    for equipamento in equipamentos:
        servico = servicos.get(equipamento.id_os_equipamento)
        fotos = servico.fotos if servico is not None else []
        itens.append({
            "id_os_equipamento": equipamento.id_os_equipamento,
            "id_servico": servico.id_servico if servico is not None else None,
            "modelo": equipamento.modelo,
            "numero_serie": equipamento.numero_serie,
            "foto_defeito": any(f.tipo == "defeito" for f in fotos),
            "conserto_salvo": servico is not None and servico.conserto_salvo_em is not None,
            "foto_conserto": any(f.tipo == "conserto" for f in fotos),
        })
    return {
        "sem_equipamento": not equipamentos,
        "equipamentos": itens,
        "pendentes_defeito": [i for i in itens if not i["foto_defeito"]],
        "pendentes_conserto": [i for i in itens if not (i["conserto_salvo"] and i["foto_conserto"])],
    }


def _lista(itens: List[Dict[str, Any]]) -> str:
    return "; ".join(f"{i['modelo']} (série {i['numero_serie']})" for i in itens)


def bloqueio_iniciar(avaliacao: Dict[str, Any]) -> Optional[str]:
    if avaliacao["sem_equipamento"]:
        return MSG_OS_SEM_EQUIPAMENTO
    if avaliacao["pendentes_defeito"]:
        return ("Não é possível iniciar o atendimento sem foto do defeito de cada equipamento. "
                f"Pendentes: {_lista(avaliacao['pendentes_defeito'])}.")
    return None


def bloqueio_finalizar(avaliacao: Dict[str, Any]) -> Optional[str]:
    if avaliacao["sem_equipamento"]:
        return MSG_OS_SEM_EQUIPAMENTO
    if avaliacao["pendentes_conserto"]:
        faltas = []
        for i in avaliacao["pendentes_conserto"]:
            partes = []
            if not i["conserto_salvo"]:
                partes.append("conserto não salvo")
            if not i["foto_conserto"]:
                partes.append("sem foto do conserto")
            faltas.append(f"{i['modelo']} (série {i['numero_serie']}): {', '.join(partes)}")
        return ("Não é possível finalizar o atendimento sem salvar o conserto e a foto do conserto de cada "
                f"equipamento. Pendentes: {'; '.join(faltas)}.")
    return None


def exigir_pronto_para_iniciar(repo: SQLRepository, chamado, visita) -> None:
    """TR-12 / RN-43: 409 com a lista de equipamentos sem foto de defeito (ou OS sem equipamento)."""
    avaliacao = avaliar_visita(repo, chamado, visita)
    mensagem = bloqueio_iniciar(avaliacao)
    if mensagem:
        raise ErroRegra(409, mensagem, "TRANSICAO_INVALIDA" if avaliacao["sem_equipamento"] else "FOTO_DEFEITO_AUSENTE")


def exigir_pronto_para_finalizar(repo: SQLRepository, chamado, visita) -> None:
    """TR-13 / RN-44: 409 com as pendências de conserto salvo e foto de conserto por equipamento."""
    avaliacao = avaliar_visita(repo, chamado, visita)
    mensagem = bloqueio_finalizar(avaliacao)
    if mensagem:
        raise ErroRegra(409, mensagem, "TRANSICAO_INVALIDA" if avaliacao["sem_equipamento"] else "CONSERTO_INCOMPLETO")
