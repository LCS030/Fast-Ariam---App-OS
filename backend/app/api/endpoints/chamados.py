"""
Rotas de OS (chamados), visitas, serviços, fotos, custos (SDD seção 6.5 a 6.10).

Camada HTTP fina: autorização por papel/atribuição, validação de entrada e delegação para os services
(`chamado_service`, `visita_service`, `custo_service`, `file_service`), que concentram as regras de domínio.

Removidos nesta versão (SDD v0.3):
  * POST /{id}/concluir            -> a OS conclui ao finalizar a volta sem pausa (RF-14 / TR-02 / PR-04).
  * DELETE /{id}                   -> substituído por POST /{id}/cancelar com motivo (PR-28).
  * POST .../finalizar-dados       -> responde 410; os dados vão em finalizar-atendimento (PR-10).
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.core.security import get_current_active_user, require_admin_role, require_technician_role
from app.db.database import get_db
from app.repositories.supabase_repository import SQLRepository
from app.schemas.chamado import (CancelarChamadoPayload, Chamado, ChamadoCreate, ChamadoUpdate, ReagendarPayload)
from app.schemas.custo import CustoTotalResponse
from app.schemas.deslocamento import FinalizarDeslocamentoPayload, IniciarDeslocamentoPayload
from app.schemas.foto import ServicoFotoListResponse, ServicoFotoResponse, UploadFotoResponse
from app.schemas.equipamento import OsEquipamento, OsEquipamentoCreate, OsEquipamentoUpdate
from app.schemas.servico_equipamento import (SalvarConsertoPayload, ServicoEquipamento, ServicoEquipamentoUpdate)
from app.schemas.visita import (FinalizarAtendimentoPayload, IniciarAtendimentoPayload, PausarPayload, Visita,
                                VisitaCreate, VisitaUpdate)
from app.services import (auditoria_service, chamado_service, custo_service, equipamento_service, file_service,
                          servico_service, visita_service)
from app.services.chamado_service import carregar_chamado, carregar_visita, exigir_status
from app.schemas.base_schemas import StatusChamado

logger = logging.getLogger(__name__)

router = APIRouter()

# upload_file: campo da visita (coluna) alimentado pelo arquivo.
SINGLE_FILE_FIELDS = [
    "odometro_inicio_url",
    "odometro_fim_url",
    "foto_inicio_ida_url",
    "foto_fim_ida_url",
    "foto_inicio_volta_url",
    "foto_fim_volta_url",
]
# upload_file: comprovantes viram registros na tabela `comprovante` (tipo -> 'pedagio' | 'frete').
COMPROVANTE_FIELDS = {
    "comprovante_pedagio_urls": "pedagio",
    "comprovante_frete_urls": "frete",
}


def get_repo(db: Session = Depends(get_db)) -> SQLRepository:
    return SQLRepository(db=db)


def _chamado_response(chamado) -> Chamado:
    resposta = Chamado.model_validate(chamado)
    resposta.cliente_nome = chamado.cliente.razao_social if chamado.cliente else None
    return resposta


def _visita_response(repo: SQLRepository, visita_id: int) -> Visita:
    return Visita.model_validate(repo.get_visita_by_id(visita_id))


def _exigir_os_nao_finalizada(chamado) -> None:
    """M4: OS Finalizada é imutável (custo congelado): não aceita novos arquivos nem alteração de serviços/materiais."""
    if chamado.status == StatusChamado.FINALIZADO:
        raise HTTPException(status_code=409,
                            detail="OS 'Finalizado' não aceita novos arquivos nem alterações de serviço.")


def _registrar_upload(repo: SQLRepository, chamado, usuario: dict, **payload) -> None:
    """Registra o upload em log_acao (mesma transação do commit). Sem PII: só ids e o campo de destino."""
    auditoria_service.registrar_acao(repo.db, id_os=chamado.id_os, usuario=usuario,
                                     acao=auditoria_service.UPLOAD_ARQUIVO, payload=payload)


def _salvar_ou_limpar(repo: SQLRepository, url: Optional[str]):
    """Executa commit; se falhar, remove o arquivo recém-gravado para não deixar órfão."""
    try:
        repo.commit()
    except Exception:
        repo.rollback()
        file_service.remover_arquivo_por_url(url)
        raise


# =====================================================================================================================
# OS: criar / listar / ler / atualizar / cancelar / reagendar
# =====================================================================================================================

@router.post("/", response_model=Chamado, status_code=201)
def create_chamado(
        chamado_in: ChamadoCreate,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Cria a OS. Sem técnico -> `Pendente`; com técnico ativo -> `Agendado` (RN-10 / T-26)."""
    chamado = chamado_service.criar_chamado(repo, chamado_in.model_dump(), admin_user)
    return _chamado_response(chamado)


@router.get("/", response_model=List[Chamado])
def get_todos_chamados(
        repo: SQLRepository = Depends(get_repo),
        is_cancelled: Optional[bool] = Query(None, description="Filtra chamados pelo status de cancelamento"),
        current_user: dict = Depends(get_current_active_user),
):
    """Admin: todas as OS. Técnico: somente as suas, nunca as canceladas (RN-12)."""
    if current_user.get("role") == "tecnico":
        chamados = repo.get_chamados(tecnico_id=current_user["user_id"], is_cancelled=False)
    else:
        chamados = repo.get_chamados(is_cancelled=is_cancelled)
    return [_chamado_response(c) for c in chamados]


@router.get("/{chamado_id}", response_model=Chamado)
def get_chamado_por_id(
        chamado_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    return _chamado_response(carregar_chamado(repo, chamado_id, current_user))


@router.patch("/{chamado_id}", response_model=Chamado)
def update_chamado(
        chamado_id: int,
        chamado_in: ChamadoUpdate,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """
    PATCH administrativo (atribuir técnico e campos cadastrais). NUNCA grava `Finalizado` (T-04) e o técnico não
    escolhe status por PATCH: usa as ações do fluxo da visita.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Técnicos não podem alterar a OS por PATCH; use as ações do fluxo da visita.")

    update_data = chamado_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    chamado = carregar_chamado(repo, chamado_id, current_user)
    atualizado = chamado_service.atualizar_chamado_admin(repo, chamado, update_data, current_user)
    return _chamado_response(repo.get_chamado_by_id(atualizado.id_os))


@router.post("/{chamado_id}/cancelar", response_model=Chamado)
def cancelar_chamado(
        chamado_id: int,
        payload: CancelarChamadoPayload,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Cancela a OS com motivo obrigatório (PR-28 / RF-11). Finalizada ou já cancelada -> 409."""
    chamado = carregar_chamado(repo, chamado_id, admin_user, permitir_cancelado=True)
    return _chamado_response(chamado_service.cancelar_chamado(repo, chamado, payload.motivo, admin_user))


@router.post("/{chamado_id}/reagendar", response_model=Visita, status_code=201)
def reagendar_chamado(
        chamado_id: int,
        payload: ReagendarPayload,
        response: Response,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """
    Reagenda a OS (admin). `Aguardando Reagendamento` -> nova visita (201), pausa encerrada, OS `Agendado`.
    `Agendado` com ida não iniciada -> altera a data da visita existente (200). Demais status -> 409.
    """
    chamado = carregar_chamado(repo, chamado_id, admin_user)
    visita, criada = chamado_service.reagendar_chamado(repo, chamado, payload.data_visita, admin_user)
    if not criada:
        response.status_code = 200
    return Visita.model_validate(visita)


@router.get("/{chamado_id}/custos", response_model=CustoTotalResponse)
def get_custos_do_chamado(
        chamado_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """OS Finalizada: devolve o snapshot imutável de `custo_os`. Demais: cálculo atual com os valores globais."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    return custo_service.obter_custo_da_os(repo.db, chamado)


@router.post("/{chamado_id}/iniciar-atendimento", response_model=Chamado)
def tecnico_inicia_atendimento(
        chamado_id: int,
        payload: Optional[IniciarAtendimentoPayload] = Body(None),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """
    Atalho no nível da OS: inicia o atendimento da visita aberta mais recente (mesmas regras de
    `.../visitas/{v}/iniciar-atendimento`: ida finalizada e OS `Agendado`).
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    exigir_status(chamado, frozenset({StatusChamado.AGENDADO}), "iniciar o atendimento")
    visita = repo.get_ultima_visita(chamado_id)
    if visita is None:
        raise HTTPException(status_code=400, detail="Não há visita para iniciar o atendimento.")
    visita_service.iniciar_atendimento(repo, chamado, visita, payload.ocorrido_em if payload else None, current_user)
    return _chamado_response(repo.get_chamado_by_id(chamado_id))


# =====================================================================================================================
# Visitas
# =====================================================================================================================

@router.post("/{chamado_id}/visitas", response_model=Visita, status_code=201)
def add_visita_ao_chamado(
        chamado_id: int,
        visita_in: VisitaCreate,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """Cria uma visita vazia (admin ou técnico atribuído). Não altera o status da OS (que deve estar `Agendado`)."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    if visita_in.servico_finalizado:
        raise HTTPException(
            status_code=400,
            detail="Não é possível criar uma visita já finalizada. A visita finaliza ao concluir o deslocamento de volta.")
    exigir_status(chamado, frozenset({StatusChamado.AGENDADO}), "criar visita")
    if repo.get_visita_aberta(chamado_id) is not None:
        raise HTTPException(
            status_code=409,
            detail="A OS já possui uma visita aberta (não finalizada); use-a ou reagende em vez de criar outra.")

    dados = visita_in.model_dump(exclude={"servico_finalizado"})
    try:
        visita = repo.create_visita(chamado_id, dados, commit=False)
        equipamento_service.garantir_servicos_da_visita(repo, chamado_id, visita)  # v0.5: 1 serviço por equipamento
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return _visita_response(repo, visita.id_visita)


@router.patch("/{chamado_id}/visitas/{visita_id}", response_model=Visita)
def update_visita_em_chamado(
        chamado_id: int,
        visita_id: int,
        visita_in: VisitaUpdate,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """
    Atualiza dados da visita (descrição, pedágio, frete, pendência e, só pelo admin e antes da ida, a data).
    NÃO finaliza a visita nem a OS: isso só acontece no fim do deslocamento de volta.
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)

    update_data = visita_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")
    if update_data.get("servico_finalizado") is True:
        raise HTTPException(
            status_code=400,
            detail="A visita não é finalizada por PATCH: ela termina ao finalizar o deslocamento de volta.")
    update_data.pop("servico_finalizado", None)

    if chamado.status == StatusChamado.FINALIZADO:
        raise HTTPException(status_code=409,
                            detail="Visita de OS 'Finalizado' não pode ser alterada (custo congelado).")
    for campo in ("data_visita", "valor_pedagio", "valor_frete_devolucao"):  # colunas NOT NULL
        if campo in update_data and update_data[campo] is None:
            update_data.pop(campo)
    if visita.servico_finalizado:
        for campo in ("valor_pedagio", "valor_frete_devolucao"):
            if campo in update_data and float(update_data[campo]) != float(getattr(visita, campo) or 0):
                raise HTTPException(
                    status_code=409,
                    detail=f"Visita encerrada: '{campo}' não pode mais ser alterado (custo e comprovantes já fechados).")
    if "data_visita" in update_data:
        if current_user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Somente o administrador altera a data da visita.")
        if visita_service.marco(visita, "ida_inicio") is not None:
            raise HTTPException(status_code=409,
                                detail="A ida já foi iniciada; a data da visita não pode mais ser alterada.")
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    try:
        repo.update_visita(visita_id, update_data, commit=False)
        if "data_visita" in update_data:  # D12: a data da OS acompanha a da visita
            repo.update_chamado(chamado_id, {"data_agendamento": update_data["data_visita"]}, commit=False)
        repo.commit()
    except Exception:
        repo.rollback()
        raise
    return _visita_response(repo, visita_id)


@router.get("/{chamado_id}/visitas/{visita_id}/estado")
def estado_visita(
        chamado_id: int,
        visita_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """Fonte de verdade dos botões do app (6.6.3)."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    return visita_service.calcular_estado(repo, chamado, visita)


@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-deslocamento")
def iniciar_deslocamento(
        chamado_id: int,
        visita_id: int,
        payload: IniciarDeslocamentoPayload,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    return visita_service.iniciar_deslocamento(repo, chamado, visita, payload.tipo, payload.km_inicio,
                                               payload.ocorrido_em)


@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-deslocamento", response_model=Visita)
def finalizar_deslocamento(
        chamado_id: int,
        visita_id: int,
        payload: FinalizarDeslocamentoPayload,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """
    Ida: fecha o trajeto. Volta: encerra a visita. Sem pausa ativa -> OS `Finalizado` + custo congelado; com pausa
    ativa -> OS `Aguardando Reagendamento` (a pausa segue ativa até reagendar).
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    resultado = visita_service.finalizar_deslocamento(repo, chamado, visita, payload.tipo, payload.km_fim,
                                                      payload.ocorrido_em, current_user)
    return Visita.model_validate(resultado)


@router.post("/{chamado_id}/visitas/{visita_id}/upload-deslocamento", response_model=Visita)
def upload_foto_deslocamento(
        chamado_id: int,
        visita_id: int,
        file: UploadFile = File(...),
        tipo: str = Form(...),  # "ida" | "volta"
        momento: str = Form(...),  # "inicio" | "fim"
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """Foto de odômetro/deslocamento (sem resolução mínima). Admin ou técnico atribuído."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    _exigir_os_nao_finalizada(chamado)
    visita_service.exigir_visita_vigente(repo, chamado, visita)
    if tipo not in ("ida", "volta"):
        raise HTTPException(status_code=400, detail="tipo inválido")
    if momento not in ("inicio", "fim"):
        raise HTTPException(status_code=400, detail="momento inválido")

    campo = f"foto_{momento}_{tipo}_url"  # ex.: foto_inicio_ida_url
    url = file_service.save_upload_file(file, f"chamado_{chamado_id}_visita_{visita_id}_{campo}")
    try:
        repo.update_visita(visita.id_visita, {campo: url}, commit=False)
        _registrar_upload(repo, chamado, current_user, id_visita=visita.id_visita, campo=campo)
    except Exception:
        file_service.remover_arquivo_por_url(url)
        raise
    _salvar_ou_limpar(repo, url)
    return _visita_response(repo, visita_id)


@router.post("/{chamado_id}/visitas/{visita_id}/upload_file", response_model=Visita)
def upload_file_visita(
        chamado_id: int,
        visita_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
        file: UploadFile = File(...),
        file_type: str = Form(..., description="Campo da visita alimentado pelo arquivo."),
):
    """
    Upload genérico. `file_type` simples (odometro_*_url, foto_*_url) grava a URL na coluna da visita;
    `comprovante_pedagio_urls` / `comprovante_frete_urls` criam um registro em `comprovante` (tipo pedagio/frete).
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    _exigir_os_nao_finalizada(chamado)
    visita_service.exigir_visita_vigente(repo, chamado, visita)
    if file_type not in SINGLE_FILE_FIELDS and file_type not in COMPROVANTE_FIELDS:
        raise HTTPException(status_code=400, detail=f"Tipo de arquivo inválido: '{file_type}'.")

    url = file_service.save_upload_file(file, f"chamado_{chamado_id}_visita_{visita_id}_{file_type}")
    try:
        if file_type in COMPROVANTE_FIELDS:
            repo.add_comprovante(visita.id_visita, COMPROVANTE_FIELDS[file_type], url, commit=False)
        else:
            repo.update_visita(visita.id_visita, {file_type: url}, commit=False)
        _registrar_upload(repo, chamado, current_user, id_visita=visita.id_visita, campo=file_type)
    except Exception:
        file_service.remover_arquivo_por_url(url)
        raise
    _salvar_ou_limpar(repo, url)
    return _visita_response(repo, visita_id)


@router.post("/{chamado_id}/visitas/{visita_id}/iniciar-atendimento", response_model=Visita)
def iniciar_atendimento_visita(
        chamado_id: int,
        visita_id: int,
        payload: Optional[IniciarAtendimentoPayload] = Body(None),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """Exige ida finalizada (400) e OS `Agendado` (409); OS -> `Em Atendimento` (RN-17 / PR-36)."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    resultado = visita_service.iniciar_atendimento(repo, chamado, visita, payload.ocorrido_em if payload else None,
                                                   current_user)
    return Visita.model_validate(resultado)


@router.post("/{chamado_id}/visitas/{visita_id}/pausar")
def pausar_visita(
        chamado_id: int,
        visita_id: int,
        payload: PausarPayload,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """
    Pausa a visita em atendimento (RN-26/29/30). Admin OU técnico atribuído. Grava quem pausou e com qual papel.
    Motivo fora da lista oficial ou "Outro" sem descrição -> 422.
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    pausa = visita_service.pausar(repo, chamado, visita, payload.motivo.value, payload.descricao,
                                  payload.ocorrido_em, current_user)
    return {
        "status": "ok",
        "id_pausa": pausa.id_pausa,
        "visita_id": pausa.visita_id,
        "motivo": pausa.motivo,
        "descricao": pausa.descricao,
        "criado_em": pausa.criado_em.isoformat() if pausa.criado_em else None,
        "is_ativa": pausa.is_ativa,
        "por_usuario_id": pausa.por_usuario_id,
        "por_papel": pausa.por_papel,
    }


@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-atendimento")
def finalizar_atendimento(
        chamado_id: int,
        visita_id: int,
        payload: FinalizarAtendimentoPayload,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """Grava nome, CPF (só dígitos) e assinatura NA VISITA. CPF inválido -> 422; pausa ativa -> 400."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    return visita_service.finalizar_atendimento(
        repo, chamado, visita, payload.nome_cliente, payload.documento_cliente, payload.assinatura_base64,
        payload.ocorrido_em, current_user)


@router.post("/{chamado_id}/visitas/{visita_id}/finalizar-dados", status_code=410)
def salvar_dados_cliente(
        chamado_id: int,
        visita_id: int,
        _current_user: dict = Depends(require_technician_role),
):
    """DESCONTINUADO (PR-10): nome, CPF e assinatura vão juntos em `finalizar-atendimento`."""
    raise HTTPException(
        status_code=410,
        detail="Rota descontinuada: envie nome_cliente, documento_cliente e assinatura_base64 em finalizar-atendimento.")


# =====================================================================================================================
# Serviços por equipamento (6.7)
# =====================================================================================================================

def _carregar_servico(repo: SQLRepository, visita, servico_id: int):
    """404 se o serviço não existe ou não pertence à visita (evita acessar serviço de outra visita/OS)."""
    servico = repo.get_servico_by_id(servico_id)
    if servico is None or servico.id_visita != visita.id_visita:
        raise HTTPException(status_code=404, detail="Serviço não encontrado nesta visita.")
    return servico


@router.get("/{chamado_id}/visitas/{visita_id}/servicos", response_model=List[ServicoEquipamento])
def listar_servicos_equipamento(
        chamado_id: int,
        visita_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    return [ServicoEquipamento.model_validate(s) for s in repo.get_servicos_by_visita(visita.id_visita)]


@router.post("/{chamado_id}/visitas/{visita_id}/servicos", status_code=410)
def criar_servico_equipamento(
        chamado_id: int,
        visita_id: int,
        _current_user: dict = Depends(require_technician_role),
):
    """
    DESCONTINUADO (v0.5, RN-42): o técnico não cadastra equipamento nem serviço. O servidor cria um registro de serviço
    por equipamento da OS quando a visita abre; use `GET .../servicos` e `PATCH .../servicos/{s}`.
    """
    raise HTTPException(
        status_code=410,
        detail=("Rota descontinuada: o equipamento vem da OS e o registro de serviço é criado pelo servidor. "
                "Use GET .../servicos e PATCH .../servicos/{id_servico}."))


@router.patch("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}", response_model=ServicoEquipamento)
def atualizar_servico_equipamento(
        chamado_id: int,
        visita_id: int,
        servico_id: int,
        payload: ServicoEquipamentoUpdate,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """
    Técnico atribuído: defeitos, descrições e materiais (nunca equipamento/série: 422). Administrador: SOMENTE
    `materiais_utilizados` e SOMENTE com a OS `Finalizado` (RN-49), recalculando o custo com os valores congelados.
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    servico = _carregar_servico(repo, visita, servico_id)
    dados = payload.model_dump(exclude_unset=True)
    if current_user.get("role") == "admin":
        servico_service.exigir_correcao_admin(chamado)
        if set(dados) != {"materiais_utilizados"} or dados["materiais_utilizados"] is None:
            raise HTTPException(
                status_code=422,
                detail=("Após a finalização o administrador só pode corrigir 'materiais_utilizados' "
                        "(fotos têm rota própria); modelo, série, defeitos e conserto não são editáveis."))
        atualizado = servico_service.corrigir_materiais_admin(repo, chamado, visita, servico,
                                                              dados["materiais_utilizados"], current_user)
    else:
        if not dados:
            raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")
        atualizado = servico_service.atualizar_servico_tecnico(repo, chamado, visita, servico, dados, current_user)
    return ServicoEquipamento.model_validate(atualizado)


@router.post("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}/salvar-conserto",
             response_model=ServicoEquipamento)
def salvar_conserto_servico(
        chamado_id: int,
        visita_id: int,
        servico_id: int,
        payload: Optional[SalvarConsertoPayload] = Body(None),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """"Salvar conserto" do equipamento (RN-47): atendimento iniciado, sem pausa, com ao menos um defeito principal."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    servico = _carregar_servico(repo, visita, servico_id)
    salvo = servico_service.salvar_conserto(repo, chamado, visita, servico,
                                            payload.ocorrido_em if payload else None, current_user)
    return ServicoEquipamento.model_validate(salvo)


@router.post("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}/upload-foto", response_model=UploadFotoResponse)
def upload_foto_servico(
        chamado_id: int,
        visita_id: int,
        servico_id: int,
        tipo: str = Form(..., description="'defeito' ou 'conserto'"),
        file: UploadFile = File(...),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """
    Foto do serviço (RN-21: 960x1280 em qualquer orientação só para `conserto`). Técnico atribuído, nas fases do
    atendimento (PR-42). Administrador: somente como correção em OS `Finalizado` (RN-49), auditada.
    """
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    servico = _carregar_servico(repo, visita, servico_id)
    eh_admin = current_user.get("role") == "admin"
    if eh_admin:
        servico_service.exigir_correcao_admin(chamado)
    else:
        _exigir_os_nao_finalizada(chamado)
        visita_service.exigir_visita_vigente(repo, chamado, visita)
    if tipo not in ("defeito", "conserto"):
        raise HTTPException(status_code=400, detail="O tipo da foto deve ser 'defeito' ou 'conserto'.")
    if not eh_admin:
        servico_service.exigir_fase_da_foto(chamado, visita, tipo)

    url = file_service.save_upload_file(
        file, f"chamado_{chamado_id}_visita_{visita_id}_servico_{servico_id}_{tipo}",
        exigir_resolucao_minima=(tipo == "conserto"))
    try:
        foto = repo.add_servico_foto(servico.id_servico, tipo, url, commit=False)
        if eh_admin:
            servico_service.registrar_foto_corrigida(repo, chamado, visita, servico, foto, "enviada", current_user)
        else:
            _registrar_upload(repo, chamado, current_user, id_visita=visita.id_visita, id_servico=servico.id_servico,
                              campo=f"foto_{tipo}")
        repo.commit()
    except Exception:
        repo.rollback()
        file_service.remover_arquivo_por_url(url)
        raise
    return UploadFotoResponse(status="ok", url=url, tipo=tipo, id_foto=foto.id_foto)


@router.delete("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}/fotos/{foto_id}", status_code=204)
def remover_foto_servico(
        chamado_id: int,
        visita_id: int,
        servico_id: int,
        foto_id: int,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Correção administrativa (RN-49): remove uma foto de OS Finalizada; nunca a última do tipo (409)."""
    chamado = carregar_chamado(repo, chamado_id, admin_user)
    visita = carregar_visita(repo, chamado, visita_id)
    servico = _carregar_servico(repo, visita, servico_id)
    servico_service.remover_foto_admin(repo, chamado, visita, servico, foto_id, admin_user)
    return Response(status_code=204)


@router.get("/{chamado_id}/visitas/{visita_id}/servicos/{servico_id}/fotos", response_model=ServicoFotoListResponse)
def get_fotos_servico(
        chamado_id: int,
        visita_id: int,
        servico_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """Fotos (defeito e conserto) de um serviço. Admin ou técnico atribuído."""
    chamado = carregar_chamado(repo, chamado_id, current_user)
    visita = carregar_visita(repo, chamado, visita_id)
    servico = _carregar_servico(repo, visita, servico_id)
    return ServicoFotoListResponse(
        fotos_defeito=[ServicoFotoResponse.model_validate(f) for f in servico.fotos if f.tipo == "defeito"],
        fotos_conserto=[ServicoFotoResponse.model_validate(f) for f in servico.fotos if f.tipo == "conserto"])


# =====================================================================================================================
# Equipamentos da OS (6.13): admin escreve; técnico atribuído só lê
# =====================================================================================================================

@router.get("/{chamado_id}/equipamentos", response_model=List[OsEquipamento])
def listar_equipamentos_da_os(
        chamado_id: int,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(get_current_active_user),
):
    """Equipamentos (modelo + série) da OS, somente leitura. Técnico só da própria OS (403 nas demais)."""
    carregar_chamado(repo, chamado_id, current_user)
    return [OsEquipamento.model_validate(e) for e in repo.get_os_equipamentos(chamado_id)]


@router.post("/{chamado_id}/equipamentos", response_model=OsEquipamento, status_code=201)
def vincular_equipamento(
        chamado_id: int,
        payload: OsEquipamentoCreate,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Vincula modelo ativo + série à OS (RN-45: até o início do atendimento; nunca em OS Finalizada/cancelada)."""
    chamado = carregar_chamado(repo, chamado_id, admin_user, permitir_cancelado=True)
    equipamento = equipamento_service.vincular(repo, chamado, payload.id_equipamento_modelo, payload.numero_serie,
                                               admin_user)
    return OsEquipamento.model_validate(equipamento)


@router.patch("/{chamado_id}/equipamentos/{os_equipamento_id}", response_model=OsEquipamento)
def atualizar_equipamento_da_os(
        chamado_id: int,
        os_equipamento_id: int,
        payload: OsEquipamentoUpdate,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")
    chamado = carregar_chamado(repo, chamado_id, admin_user, permitir_cancelado=True)
    equipamento = equipamento_service.atualizar_vinculo(repo, chamado, os_equipamento_id, dados, admin_user)
    return OsEquipamento.model_validate(equipamento)


@router.delete("/{chamado_id}/equipamentos/{os_equipamento_id}", status_code=204)
def remover_equipamento_da_os(
        chamado_id: int,
        os_equipamento_id: int,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    chamado = carregar_chamado(repo, chamado_id, admin_user, permitir_cancelado=True)
    equipamento_service.remover_vinculo(repo, chamado, os_equipamento_id, admin_user)
    return Response(status_code=204)
