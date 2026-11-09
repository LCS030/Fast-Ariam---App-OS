from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Any
from app.db.database import get_db
from app.models.tecnico import Tecnico as TecnicoModel
from app.core.security import (
    verify_password,
    verify_password_dummy,
    create_access_token,
    get_current_active_user,
)
from app.schemas.base_schemas import UserRole
from app.schemas.tecnico import UsuarioAtual
from app.schemas.token import Token

router = APIRouter()

# Mensagem única (SEG-02 / PR-21): e-mail inexistente, senha errada e usuário inativo são indistinguíveis.
MENSAGEM_LOGIN_INVALIDO = "Email ou senha incorretos"


def _login_invalido() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=MENSAGEM_LOGIN_INVALIDO,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
) -> Any:
    """
    Autentica um usuário (técnico/admin) e retorna um token JWT.
    Espera dados de formulário: 'username' (será o email) e 'password'.

    Falhas (e-mail inexistente, senha incorreta ou usuário inativo) retornam sempre 401 com a mesma mensagem.
    """
    email = form_data.username.strip().lower()

    # Busca somente pelo e-mail (PR-23), sem varrer todos os técnicos.
    user = db.query(TecnicoModel).filter(func.lower(TecnicoModel.email) == email).first()

    if user is None:
        # Gasta o mesmo tempo de bcrypt de um login real para não permitir enumeração de e-mails por tempo.
        verify_password_dummy(form_data.password)
        raise _login_invalido()

    senha_confere = verify_password(form_data.password, user.password_hash)
    if not senha_confere or not user.is_active:
        raise _login_invalido()

    role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
    access_token_data = {
        "sub": user.email,  # Nesse caso (do token), o sub (subject) é o e-mail e não o id.
        "user_id": user.id_tecnico,
        "role": role,
    }

    access_token = create_access_token(data=access_token_data)

    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=UsuarioAtual)
def read_current_user(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
) -> Any:
    """
    Retorna o usuário autenticado: {id_tecnico, nome, email, role, is_active} (SDD 6.2, PR-06).
    Nunca inclui dados bancários, CPF/CNPJ ou telefone (SEG-10).
    """
    usuario = db.get(TecnicoModel, current_user["user_id"])
    if usuario is None:  # a dependência já validou; proteção contra corrida de remoção
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Não foi possível validar as credenciais",
                            headers={"WWW-Authenticate": "Bearer"})
    return usuario
