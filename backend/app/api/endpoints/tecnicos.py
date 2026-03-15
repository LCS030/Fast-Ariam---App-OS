from fastapi import APIRouter, Depends, HTTPException, Response, Query
from typing import List, Optional
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.repositories.mysql_repository import SQLRepository
from app.schemas.base_schemas import UserRole
# from app.repositories.in_memory_repository import InMemoryRepository
from app.schemas.tecnico import Tecnico, TecnicoCreate, TecnicoUpdate
from app.core.security import hash_password, require_admin_role, get_current_active_user, verify_password
from app.schemas.token import PasswordUpdate

router = APIRouter()


# Função de injeção para o repositório de técnicos
# def get_tecnico_repository():
#     return InMemoryRepository("tecnicos")
def get_tecnico_repository(db: Session = Depends(get_db)):
    """Dependência para criar e retornar uma instância do SQLRepository com uma sessão do banco de dados."""
    return SQLRepository(db=db)


@router.post("/", response_model=Tecnico, status_code=201)
def create_tecnico(
        tecnico_in: TecnicoCreate,
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        admin_user: dict = Depends(require_admin_role)
):
    tecnico_data = tecnico_in.model_dump()
    plain_password = tecnico_data.pop("password")
    tecnico_data["password_hash"] = hash_password(plain_password)
    if 'role' in tecnico_data:
        tecnico_data['role'] = UserRole(tecnico_data['role'])
    # tecnico_criado_dict = repo.create(tecnico_data)
    tecnico_criado_db = repo.create_tecnico(tecnico_data)
    # return Tecnico(**tecnico_criado_dict)
    return tecnico_criado_db


@router.get("/", response_model=List[Tecnico])
def get_todos_tecnicos(
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        is_active: Optional[bool] = Query(None, description="Filtra técnicos pelo status de atividade"),
        admin_user: dict = Depends(require_admin_role)
):
    # tecnicos_list = repo.get_all(is_active=is_active)
    tecnicos_list = repo.get_tecnicos(is_active=is_active)
    # return [Tecnico(**tecnico) for tecnico in tecnicos_list]
    return tecnicos_list


@router.get("/{tecnico_id}", response_model=Tecnico)
def get_tecnico_por_id(
        tecnico_id: int,
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        admin_user: dict = Depends(require_admin_role)
):
    # tecnico_encontrado = repo.get_by_id(tecnico_id)
    tecnico_encontrado = repo.get_tecnico_by_id(tecnico_id)
    if not tecnico_encontrado:
        raise HTTPException(status_code=404, detail="Técnico não encontrado")

    # return Tecnico(**tecnico_encontrado)
    return tecnico_encontrado


@router.patch("/{tecnico_id}", response_model=Tecnico)
def update_tecnico(
        tecnico_id: int,
        tecnico_in: TecnicoUpdate,
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        admin_user: dict = Depends(require_admin_role)
):
    update_data = tecnico_in.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    # updated_tecnico = repo.update(tecnico_id, update_data)
    updated_tecnico = repo.update_tecnico(tecnico_id, update_data)
    if updated_tecnico is None:
        raise HTTPException(status_code=404, detail="Técnico não encontrado.")

    # return Tecnico(**updated_tecnico)
    return updated_tecnico


@router.patch("/me/password", status_code=204)
def update_current_user_password(
        password_data: PasswordUpdate,
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        current_user: dict = Depends(get_current_active_user)
):
    """
    Permite que o usuário logado altere sua própria senha.
    """
    user_id = current_user.get("user_id")

    # user_db = repo.get_by_id(user_id)
    user_db = repo.get_tecnico_by_id(user_id)
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # current_hash = user_db.get("password_hash")
    current_hash = user_db.password_hash
    if not verify_password(password_data.old_password, current_hash):
        raise HTTPException(status_code=400, detail="Senha antiga incorreta.")

    new_password_hash = hash_password(password_data.new_password)
    # repo.update(user_id, {"password_hash": new_password_hash})
    user_db.password_hash = new_password_hash
    repo.db.add(user_db)
    repo.db.commit()

    return Response(status_code=204)


@router.delete("/{tecnico_id}", status_code=204)
def delete_tecnico(
        tecnico_id: int,
        # repo: InMemoryRepository = Depends(get_tecnico_repository),
        repo: SQLRepository = Depends(get_tecnico_repository),
        admin_user: dict = Depends(require_admin_role)
):
    """
    Soft delete para o técnico.
    """
    # success = repo.delete(tecnico_id)
    success = repo.delete_tecnico(tecnico_id)
    if not success:
        raise HTTPException(status_code=404, detail="Técnico não encontrado.")
    return Response(status_code=204)
