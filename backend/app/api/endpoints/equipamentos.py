"""
Catálogo de modelos de equipamento (SDD 6.13, PRD RF-23 / RN-40). Somente o administrador acessa; o técnico recebe os
equipamentos embutidos na OS (menor privilégio). Nunca exclui: `DELETE` é desativação lógica.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.security import require_admin_role
from app.db.database import get_db
from app.repositories.supabase_repository import SQLRepository
from app.schemas.equipamento import EquipamentoModelo, EquipamentoModeloCreate, EquipamentoModeloUpdate
from app.services import equipamento_service

router = APIRouter()


def get_repo(db: Session = Depends(get_db)) -> SQLRepository:
    return SQLRepository(db=db)


@router.post("/", response_model=EquipamentoModelo, status_code=201)
def criar_modelo(
        payload: EquipamentoModeloCreate,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Cria um modelo no catálogo. Nome duplicado (sem diferenciar maiúsculas/espaços nas pontas) -> 409."""
    return EquipamentoModelo.model_validate(equipamento_service.criar_modelo(repo, payload.modelo, admin_user))


@router.get("/", response_model=List[EquipamentoModelo])
def listar_modelos(
        is_active: Optional[bool] = Query(None, description="Filtra por ativos/inativos; omitido lista todos."),
        repo: SQLRepository = Depends(get_repo),
        _admin: dict = Depends(require_admin_role),
):
    return [EquipamentoModelo.model_validate(m) for m in repo.get_modelos(is_active=is_active)]


@router.get("/{modelo_id}", response_model=EquipamentoModelo)
def obter_modelo(
        modelo_id: int,
        repo: SQLRepository = Depends(get_repo),
        _admin: dict = Depends(require_admin_role),
):
    modelo = repo.get_modelo_by_id(modelo_id)
    if modelo is None:
        raise HTTPException(status_code=404, detail=f"Modelo de equipamento {modelo_id} não encontrado.")
    return EquipamentoModelo.model_validate(modelo)


@router.patch("/{modelo_id}", response_model=EquipamentoModelo)
def atualizar_modelo(
        modelo_id: int,
        payload: EquipamentoModeloUpdate,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Renomeia (reescreve o histórico exibido, auditado) e/ou ativa/desativa o modelo."""
    dados = payload.model_dump(exclude_unset=True)
    if not dados:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")
    return EquipamentoModelo.model_validate(equipamento_service.atualizar_modelo(repo, modelo_id, dados, admin_user))


@router.delete("/{modelo_id}", status_code=204)
def desativar_modelo(
        modelo_id: int,
        repo: SQLRepository = Depends(get_repo),
        admin_user: dict = Depends(require_admin_role),
):
    """Desativação lógica: o modelo continua nas OS existentes, mas não pode ser vinculado a OS novas."""
    equipamento_service.atualizar_modelo(repo, modelo_id, {"is_active": False}, admin_user)
    return Response(status_code=204)
