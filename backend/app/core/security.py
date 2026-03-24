import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash salvo."""
    try:
        password_bytes = plain_password.encode('utf-8')
        hashed_password_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(password_bytes, hashed_password_bytes)
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    """Gera o hash de uma senha em texto puro."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')


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
    """Decodifica um token JWT e retorna o payload (dados)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Dependência para obter o usuário atual a partir do token JWT.
    Valida o token e retorna o payload (dados do usuário).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        if payload is None:
            raise credentials_exception
        return payload
    except Exception as e:
        raise credentials_exception  # TODO: Fazer a busca para saber se o usuário existe
    # return payload


async def get_current_active_user(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Dependência que garante que o usuário obtido do token está ativo.
    """
    # TODO: Buscar usuário no repositório
    return current_user


# TODO: MOMENTANEAMENTE SEM USO. Mantendo par ver se será útil. A lambda nos depends de require_admin_role e require_technician_role não é uma coroutine (não faz await), mesmo que as funções sejam async, lambda não é.
async def require_role(required_role: str, user: dict = Depends(get_current_active_user)) -> dict:
    """
    Dependência genérica que verifica se o usuário logado tem o role necessária.
    """
    user_role = user.get("role")
    if user_role != required_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado: Requer privilégios de '{required_role}'."
        )
    return user


async def require_admin_role(user: dict = Depends(get_current_active_user)) -> dict:
    """
    Dependência que exige que o usuário logado tenha o role 'admin'.
    Obtém o usuário ativo e verifica seu role.
    """
    user_role = user.get("role")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: Requer privilégios de 'admin'."
        )
    return user


async def require_technician_role(user: dict = Depends(get_current_active_user)) -> dict:
    """
    Dependência que exige que o usuário logado tenha o role 'tecnico'.
    Obtém o usuário ativo e verifica seu role.
    """
    user_role = user.get("role")
    if user_role != "tecnico":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: Requer privilégios de 'tecnico'."
        )
    return user
