from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from app.schemas.cliente import Cliente, ClienteCreate, ClienteUpdate
from app.models.cliente import Cliente as ClienteModel
from app.models.chamado import OrdemServico
from app.core.security import require_admin_role, get_current_active_user
from app.db.database import get_db

router = APIRouter()

# Observação de arquitetura: estes endpoints usam a Session diretamente (e não o SQLRepository, de propriedade do
# Backend A) para tratar duplicidade de `codigo` (409) e a regra de acesso do técnico (SEG-11).


def _garantir_codigo_unico(db: Session, codigo: int, excluir_id: Optional[int] = None) -> None:
    """RN-04: `codigo` é único. Retorna 409 amigável (e não 500 por IntegrityError)."""
    query = db.query(ClienteModel.id_cliente).filter(ClienteModel.codigo == codigo)
    if excluir_id is not None:
        query = query.filter(ClienteModel.id_cliente != excluir_id)
    if query.first():
        raise HTTPException(status_code=409, detail=f"Já existe um cliente cadastrado com o código {codigo}.")


def _commit_ou_409(db: Session) -> None:
    """Commit que converte violação de UNIQUE concorrente em 409 (sem expor detalhes internos do banco)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Já existe um cliente cadastrado com este código.")


@router.post("/", response_model=Cliente, status_code=201)
def create_cliente(
        cliente_in: ClienteCreate,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    _garantir_codigo_unico(db, cliente_in.codigo)
    novo = ClienteModel(**cliente_in.model_dump())
    db.add(novo)
    _commit_ou_409(db)
    db.refresh(novo)
    return novo


@router.get("/", response_model=List[Cliente])
def get_todos_clientes(
        db: Session = Depends(get_db),
        is_active: Optional[bool] = Query(None, description="Filtra clientes pelo status de atividade"),
        admin_user: dict = Depends(require_admin_role)
):
    query = db.query(ClienteModel)
    if is_active is not None:
        query = query.filter(ClienteModel.is_active == is_active)
    return query.order_by(ClienteModel.id_cliente).all()


@router.get("/{cliente_id}", response_model=Cliente)
def get_cliente_por_id(
        cliente_id: int,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """
    Admin lê qualquer cliente. Técnico só lê clientes que tenham OS (não cancelada) atribuída a ele (SEG-11);
    caso contrário 403, inclusive quando o cliente não existe (não revela quais ids existem).
    """
    if current_user.get("role") != "admin":
        tem_os = db.query(OrdemServico.id_os).filter(
            OrdemServico.id_cliente == cliente_id,
            OrdemServico.id_tecnico_atribuido == current_user["user_id"],
            OrdemServico.is_cancelled.is_(False),
        ).first()
        if not tem_os:
            raise HTTPException(status_code=403, detail="Acesso negado a este cliente.")

    cliente_encontrado = db.get(ClienteModel, cliente_id)
    if not cliente_encontrado:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    return cliente_encontrado


@router.patch("/{cliente_id}", response_model=Cliente)
def update_cliente(
        cliente_id: int,
        cliente_in: ClienteUpdate,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    update_data = cliente_in.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    cliente = db.get(ClienteModel, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    if "codigo" in update_data and update_data["codigo"] != cliente.codigo:
        _garantir_codigo_unico(db, update_data["codigo"], excluir_id=cliente.id_cliente)

    for campo, valor in update_data.items():
        setattr(cliente, campo, valor)

    _commit_ou_409(db)
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=204)
def delete_cliente(
        cliente_id: int,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    """Desativação lógica (RN-05): o cliente continua existindo para as OS já vinculadas."""
    cliente = db.get(ClienteModel, cliente_id)
    if cliente is None:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    cliente.is_active = False
    db.commit()

    return Response(status_code=204)
