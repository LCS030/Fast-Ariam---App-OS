import bcrypt
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from typing import Callable, Optional
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db.database import get_db
from app.models.tecnico import Tecnico
from app.schemas.base_schemas import UserRole


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash salvo."""
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_password_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_password_bytes)
    except (ValueError, TypeError, AttributeError):
        return False


def hash_password(password: str) -> str:
    """Gera o hash de uma senha em texto puro."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Hash descartável usado para gastar o mesmo tempo de bcrypt quando o e-mail não existe (SEG-02)."""
    return hash_password("fast-ariam-dummy-password")


def verify_password_dummy(plain_password: str) -> None:
    """Executa um checkpw sem efeito: evita enumeração de usuários por tempo de resposta no login."""
    verify_password(plain_password, _dummy_password_hash())


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Cria um novo token JWT."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str):
    """Decodifica um token JWT e retorna o payload (dados). Retorna None se inválido ou expirado."""
    try:
        # Somente o algoritmo configurado é aceito (nunca o declarado no cabeçalho do token) e 'exp' é obrigatório.
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"require_exp": True})
        return payload
    except JWTError:
        return None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _credentials_exception() -> HTTPException:
    # Mensagem única para token inválido, expirado, usuário inexistente ou inativo (não vaza o motivo).
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> dict:
    """
    Dependência para obter o usuário atual a partir do token JWT (SEG-01 / PR-05).

    A cada requisição o usuário é consultado no banco: técnico/admin inexistente ou inativo recebe 401, mesmo com um
    token ainda dentro da validade. O papel (`role`) vem do banco, nunca do token: uma mudança de papel vale na
    requisição seguinte.

    Retorna um dict compatível com os endpoints existentes: {"sub", "user_id", "role", ...}.
    É síncrona de propósito (acessa o banco com Session síncrona): o FastAPI a executa em thread auxiliar e não
    bloqueia o event loop.
    """
    payload = decode_access_token(token)
    if not payload:
        raise _credentials_exception()

    user_id = payload.get("user_id")
    subject = payload.get("sub")
    if isinstance(user_id, bool) or not isinstance(user_id, int) or not isinstance(subject, str):
        raise _credentials_exception()

    tecnico = db.get(Tecnico, user_id)
    if tecnico is None or not tecnico.is_active:
        raise _credentials_exception()

    # O e-mail do token precisa ser o atual do cadastro (se o e-mail mudou, o token antigo deixa de valer).
    if (tecnico.email or "").lower() != subject.lower():
        raise _credentials_exception()

    role = tecnico.role.value if isinstance(tecnico.role, UserRole) else str(tecnico.role)
    return {
        "sub": tecnico.email,
        "user_id": tecnico.id_tecnico,
        "role": role,
        "nome": tecnico.nome,
        "is_active": True,
    }


def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependência que garante usuário ativo. A checagem de existência/atividade já é feita em `get_current_user`;
    esta dependência permanece como ponto de entrada estável usado pelos endpoints.
    """
    if not current_user.get("is_active"):
        raise _credentials_exception()
    return current_user


def require_role(required_role: str) -> Callable[..., dict]:
    """
    Fábrica de dependência que exige um papel específico (RBAC no servidor).
    Uso: `Depends(require_role("admin"))`.
    """

    def _dependency(user: dict = Depends(get_current_active_user)) -> dict:
        if user.get("role") != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acesso negado: Requer privilégios de '{required_role}'."
            )
        return user

    return _dependency


# Dependências prontas para uso nos routers: `Depends(require_admin_role)` / `Depends(require_technician_role)`.
require_admin_role = require_role("admin")
require_technician_role = require_role("tecnico")
