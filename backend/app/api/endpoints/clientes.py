from fastapi import APIRouter, Depends, HTTPException, Query, Response
from typing import List, Optional
from sqlalchemy.orm import Session
from app.schemas.cliente import Cliente, ClienteCreate, ClienteUpdate
from app.repositories.supabase_repository import SQLRepository
from app.core.security import require_admin_role, get_current_active_user
from app.db.database import get_db

router = APIRouter()


def get_cliente_repository(db: Session = Depends(get_db)):
    """Dependência para criar e retornar uma instância do SQLRepository com uma sessão do banco de dados."""
    return SQLRepository(db=db)


@router.post("/", response_model=Cliente, status_code=201)
def create_cliente(
        cliente_in: ClienteCreate,
        repo: SQLRepository = Depends(get_cliente_repository),
        admin_user: dict = Depends(require_admin_role)
):
    cliente_data = cliente_in.model_dump()
    cliente_criado_db = repo.create_cliente(cliente_data)
    return cliente_criado_db


@router.get("/", response_model=List[Cliente])
def get_todos_clientes(
        repo: SQLRepository = Depends(get_cliente_repository),
        is_active: Optional[bool] = Query(None, description="Filtra clientes pelo status de atividade"),
        admin_user: dict = Depends(require_admin_role)
):
    clientes_list = repo.get_clientes(is_active=is_active)
    return clientes_list


@router.get("/{cliente_id}", response_model=Cliente)
def get_cliente_por_id(
        cliente_id: int,
        repo: SQLRepository = Depends(get_cliente_repository),
        current_user: dict = Depends(get_current_active_user)
):
    cliente_encontrado = repo.get_cliente_by_id(cliente_id)
    if not cliente_encontrado:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return cliente_encontrado


@router.patch("/{cliente_id}", response_model=Cliente)
def update_cliente(
        cliente_id: int,
        cliente_in: ClienteUpdate,
        repo: SQLRepository = Depends(get_cliente_repository),
        admin_user: dict = Depends(require_admin_role)
):
    updated_cliente = repo.update_cliente(cliente_id, cliente_in)
    if updated_cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return updated_cliente


@router.delete("/{cliente_id}", status_code=204)
def delete_cliente(
        cliente_id: int,
        repo: SQLRepository = Depends(get_cliente_repository),
        admin_user: dict = Depends(require_admin_role)
):
    success = repo.delete_cliente(cliente_id)
    if not success:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return Response(status_code=204)
