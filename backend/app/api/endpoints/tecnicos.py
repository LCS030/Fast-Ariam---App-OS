from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db.database import get_db
from app.models.tecnico import Tecnico as TecnicoModel
from app.schemas.base_schemas import UserRole
from app.schemas.tecnico import Tecnico, TecnicoCreate, TecnicoUpdate
from app.core.security import hash_password, require_admin_role, get_current_active_user, verify_password
from app.schemas.token import PasswordUpdate
from app.services.chamado_service import desatribuir_os_do_tecnico

router = APIRouter()

# Observação de arquitetura: estes endpoints usam a Session diretamente (e não o SQLRepository, de propriedade do
# Backend A) porque precisam de consultas específicas (e-mail case-insensitive, contagem de admins ativos) e porque
# `SQLRepository.update_tecnico` espera um TecnicoUpdate enquanto o endpoint sempre lhe passou um dict.


# --- Helpers ----------------------------------------------------------------------------------------------------------

def _get_tecnico_or_404(db: Session, tecnico_id: int) -> TecnicoModel:
    tecnico = db.get(TecnicoModel, tecnico_id)
    if tecnico is None:
        raise HTTPException(status_code=404, detail="Técnico não encontrado.")
    return tecnico


def _garantir_email_cnpj_unicos(db: Session, email: Optional[str], cnpj: Optional[str],
                                excluir_id: Optional[int] = None) -> None:
    """RN-06: e-mail e CNPJ são únicos entre técnicos. Retorna 409 amigável (e não 500 por IntegrityError)."""
    if email is not None:
        query = db.query(TecnicoModel.id_tecnico).filter(func.lower(TecnicoModel.email) == email.lower())
        if excluir_id is not None:
            query = query.filter(TecnicoModel.id_tecnico != excluir_id)
        if query.first():
            raise HTTPException(status_code=409, detail="Já existe um técnico cadastrado com este e-mail.")
    if cnpj is not None:
        query = db.query(TecnicoModel.id_tecnico).filter(TecnicoModel.cnpj == cnpj)
        if excluir_id is not None:
            query = query.filter(TecnicoModel.id_tecnico != excluir_id)
        if query.first():
            raise HTTPException(status_code=409, detail="Já existe um técnico cadastrado com este CNPJ.")


def _commit_ou_409(db: Session) -> None:
    """Commit que converte violação de UNIQUE concorrente em 409 (sem expor detalhes internos do banco)."""
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="E-mail ou CNPJ já cadastrado para outro técnico.")


def _qtd_admins_ativos(db: Session) -> int:
    return db.query(func.count(TecnicoModel.id_tecnico)).filter(
        TecnicoModel.role == UserRole.ADMIN, TecnicoModel.is_active.is_(True)
    ).scalar() or 0


def _garantir_admin_nao_se_remove(db: Session, alvo: TecnicoModel, admin_logado_id: int,
                                  novo_ativo: bool, novo_role: UserRole) -> None:
    """
    Proposta (registrada como dúvida ao PO, não consta no PRD): um administrador não pode desativar a si mesmo nem
    rebaixar o próprio papel, e o sistema nunca pode ficar sem administrador ativo (evita lock-out total).
    """
    era_admin_ativo = alvo.is_active and alvo.role == UserRole.ADMIN
    continua_admin_ativo = novo_ativo and novo_role == UserRole.ADMIN
    if not era_admin_ativo or continua_admin_ativo:
        return
    if alvo.id_tecnico == admin_logado_id:
        raise HTTPException(
            status_code=400,
            detail="Um administrador não pode desativar a própria conta nem remover o próprio papel de administrador."
        )
    if _qtd_admins_ativos(db) <= 1:
        raise HTTPException(status_code=400, detail="Não é possível remover o último administrador ativo do sistema.")


# --- Rotas ------------------------------------------------------------------------------------------------------------
# As rotas fixas (/me/...) são declaradas ANTES das rotas com parâmetro (/{tecnico_id}).

@router.post("/", response_model=Tecnico, status_code=201)
def create_tecnico(
        tecnico_in: TecnicoCreate,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    _garantir_email_cnpj_unicos(db, tecnico_in.email, tecnico_in.cnpj)

    data = tecnico_in.model_dump()
    plain_password = data.pop("password")
    dados_bancarios = data.pop("dados_bancarios")
    data["password_hash"] = hash_password(plain_password)
    data["role"] = UserRole(data["role"])
    data.update(
        banco=dados_bancarios["banco"],
        agencia=dados_bancarios["agencia"],
        conta=dados_bancarios["conta"],
        pix=dados_bancarios.get("pix"),
    )

    novo = TecnicoModel(**data)
    db.add(novo)
    _commit_ou_409(db)
    db.refresh(novo)
    return novo


@router.get("/", response_model=List[Tecnico])
def get_todos_tecnicos(
        db: Session = Depends(get_db),
        is_active: Optional[bool] = Query(None, description="Filtra técnicos pelo status de atividade"),
        admin_user: dict = Depends(require_admin_role)
):
    query = db.query(TecnicoModel)
    if is_active is not None:
        query = query.filter(TecnicoModel.is_active == is_active)
    return query.order_by(TecnicoModel.id_tecnico).all()


@router.patch("/me/password", status_code=204)
def update_current_user_password(
        password_data: PasswordUpdate,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_active_user)
):
    """
    Permite que o usuário logado altere sua própria senha (valida a senha atual; nova senha com 8+ caracteres).
    """
    user_db = db.get(TecnicoModel, current_user["user_id"])
    if not user_db:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if not verify_password(password_data.old_password, user_db.password_hash):
        raise HTTPException(status_code=400, detail="Senha antiga incorreta.")

    user_db.password_hash = hash_password(password_data.new_password)
    db.add(user_db)
    db.commit()

    return Response(status_code=204)


@router.get("/{tecnico_id}", response_model=Tecnico)
def get_tecnico_por_id(
        tecnico_id: int,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    return _get_tecnico_or_404(db, tecnico_id)


@router.patch("/{tecnico_id}", response_model=Tecnico)
def update_tecnico(
        tecnico_id: int,
        tecnico_in: TecnicoUpdate,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    """Atualização parcial pelo administrador (único papel que altera cadastro e dados bancários, RN-07)."""
    update_data = tecnico_in.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar foi fornecido.")

    tecnico = _get_tecnico_or_404(db, tecnico_id)

    novo_ativo = update_data.get("is_active", tecnico.is_active)
    novo_role = UserRole(update_data.get("role", tecnico.role))
    _garantir_admin_nao_se_remove(db, tecnico, admin_user["user_id"], novo_ativo, novo_role)

    novo_email = update_data.get("email")
    novo_cnpj = update_data.get("cnpj")
    _garantir_email_cnpj_unicos(
        db,
        novo_email if novo_email and novo_email.lower() != (tecnico.email or "").lower() else None,
        novo_cnpj if novo_cnpj and novo_cnpj != tecnico.cnpj else None,
        excluir_id=tecnico.id_tecnico,
    )

    dados_bancarios = update_data.pop("dados_bancarios", None) or {}
    for campo in ("banco", "agencia", "conta", "pix"):
        if campo in dados_bancarios:
            setattr(tecnico, campo, dados_bancarios[campo])

    desativando = tecnico.is_active and update_data.get("is_active") is False
    for campo, valor in update_data.items():
        setattr(tecnico, campo, UserRole(valor) if campo == "role" else valor)
    if desativando:
        # RN-08a: desatribui as OS não finalizadas na MESMA transação da desativação.
        desatribuir_os_do_tecnico(db, tecnico.id_tecnico, admin_user)

    _commit_ou_409(db)
    db.refresh(tecnico)
    return tecnico


@router.delete("/{tecnico_id}", status_code=204)
def delete_tecnico(
        tecnico_id: int,
        db: Session = Depends(get_db),
        admin_user: dict = Depends(require_admin_role)
):
    """
    Desativação lógica do técnico (SDD 6.3). As sessões existentes deixam de valer na requisição seguinte, pois
    o usuário ativo é verificado no banco a cada chamada (SEG-01).

    RN-08a (aprovada): na mesma transação, as OS do técnico não finalizadas e não canceladas voltam a `Pendente`
    sem técnico (histórico de visitas/fotos/serviços/pausas preservado) e a ação é auditada em log_acao.
    """
    tecnico = _get_tecnico_or_404(db, tecnico_id)
    if tecnico.is_active:
        _garantir_admin_nao_se_remove(db, tecnico, admin_user["user_id"], False, UserRole(tecnico.role))
        tecnico.is_active = False
        desatribuir_os_do_tecnico(db, tecnico.id_tecnico, admin_user)
        db.commit()
    return Response(status_code=204)
