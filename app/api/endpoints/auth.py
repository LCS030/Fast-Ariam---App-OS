from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from typing import Any
from app.repositories.supabase_repository import SQLRepository
from app.core.security import verify_password, create_access_token
from app.schemas.token import Token
from app.api.endpoints.tecnicos import get_tecnico_repository

router = APIRouter()

@router.post("/login", response_model=Token)
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    repo: SQLRepository = Depends(get_tecnico_repository)
) -> Any:
    """
    Autentica um usuário (técnico) e retorna um token JWT.
    Espera dados de formulário: 'username' (será o email) e 'password'.
    """
    tecnicos = repo.get_tecnicos(is_active=None)
    user = None
    for tecnico in tecnicos:
        if tecnico.email.lower() == form_data.username.lower():
            if not tecnico.is_active:
                 raise HTTPException(status_code=400, detail="Usuário inativo")
            if verify_password(form_data.password, tecnico.password_hash):
                 user = tecnico
                 break
            else:
                 raise HTTPException(
                     status_code=status.HTTP_401_UNAUTHORIZED,
                     detail="Email ou senha incorretos",
                     headers={"WWW-Authenticate": "Bearer"},
                 )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )


    access_token_data = {
        "sub": user.email, # Nesse caso (do token), o sub (subject) é o identificador único e não o id.
        "user_id": user.id_tecnico,
        "role": user.role,
    }

    access_token = create_access_token(data=access_token_data)

    return {"access_token": access_token, "token_type": "bearer"}