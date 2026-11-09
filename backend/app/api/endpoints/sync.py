"""
Sincronização offline do app do técnico (SDD 6.12): arquivos, eventos e cache de OS. Somente o papel `tecnico`.
"""
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import require_technician_role
from app.db.database import get_db
from app.models.sync_arquivo import SyncArquivo, TIPOS_ARQUIVO
from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.schemas.sync import LoteSync, RespostaArquivo, RespostaLote
from app.services import file_service, sync_service
from app.services.chamado_service import carregar_chamado, carregar_visita

logger = logging.getLogger(__name__)

router = APIRouter()


def get_repo(db: Session = Depends(get_db)) -> SQLRepository:
    return SQLRepository(db=db)


@router.post("/arquivos", response_model=RespostaArquivo)
def receber_arquivo(
        client_file_id: UUID = Form(..., description="UUID gerado no aparelho (idempotência)."),
        tipo_arquivo: str = Form(..., description=" | ".join(TIPOS_ARQUIVO)),
        id_os: int = Form(...),
        id_visita: int = Form(...),
        file: UploadFile = File(...),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """
    Recebe e valida o arquivo (JPEG/PNG real, 15 MB; conserto 960x1280 em qualquer orientação) e o associa ao
    `client_file_id`. A ligação ao registro final ocorre quando o evento que o referencia é aplicado (SY-08).
    Reenviar o mesmo `client_file_id` devolve a url já gravada (`duplicado`).
    """
    existente = repo.db.get(SyncArquivo, client_file_id)
    if existente is not None:
        if existente.id_tecnico != current_user["user_id"]:
            raise HTTPException(status_code=403, detail="client_file_id já utilizado por outro dispositivo.")
        return RespostaArquivo(client_file_id=client_file_id, url=existente.url, resultado=sync_service.DUPLICADO)
    if tipo_arquivo not in TIPOS_ARQUIVO:
        raise HTTPException(status_code=422, detail=f"tipo_arquivo inválido. Use: {', '.join(TIPOS_ARQUIVO)}.")

    # OS cancelada: o arquivo é aceito e guardado (nunca descartado em silêncio, SY-06); o EVENTO que o referencia é que
    # será rejeitado com OS_CANCELADA. Inexistente -> 404; de outro técnico -> 403.
    chamado = carregar_chamado(repo, id_os, current_user, permitir_cancelado=True)
    visita = carregar_visita(repo, chamado, id_visita)  # 404
    if chamado.status == StatusChamado.FINALIZADO:
        raise HTTPException(status_code=409, detail="OS 'Finalizado' não aceita novos arquivos.")

    prefixo = f"chamado_{id_os}_visita_{id_visita}_sync_{tipo_arquivo}"
    if tipo_arquivo == "assinatura":
        url = file_service.salvar_assinatura(file_service.validar_imagem_upload(file))
    else:
        url = file_service.save_upload_file(file, prefixo, exigir_resolucao_minima=(tipo_arquivo == "foto_conserto"))
    try:
        repo.db.add(SyncArquivo(client_file_id=client_file_id, id_tecnico=current_user["user_id"], id_os=id_os,
                                id_visita=visita.id_visita, tipo_arquivo=tipo_arquivo, url=url))
        repo.commit()
    except IntegrityError:  # reenvio simultâneo do mesmo client_file_id
        repo.rollback()
        file_service.remover_arquivo_por_url(url)
        existente = repo.db.get(SyncArquivo, client_file_id)
        if existente is None:
            raise
        return RespostaArquivo(client_file_id=client_file_id, url=existente.url, resultado=sync_service.DUPLICADO)
    except Exception:
        repo.rollback()
        file_service.remover_arquivo_por_url(url)
        raise
    return RespostaArquivo(client_file_id=client_file_id, url=url, resultado=sync_service.APLICADO)


@router.post("/eventos", response_model=RespostaLote)
def receber_eventos(
        lote: LoteSync,
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """Processa o lote de eventos (por `ocorrido_em`, idempotente por `client_event_id`). Sempre 200 por lote."""
    return RespostaLote(resultados=sync_service.processar_lote(repo, current_user, lote))


@router.get("/minhas-os")
def minhas_os(
        desde: Optional[datetime] = Query(None, description="Aceito, mas ainda não filtra: devolve sempre o conjunto completo."),
        repo: SQLRepository = Depends(get_repo),
        current_user: dict = Depends(require_technician_role),
):
    """Todas as OS atribuídas ao técnico (não canceladas) com equipamentos, visitas, serviços e estado da visita vigente."""
    return sync_service.minhas_os(repo, current_user)
