# app/core/security.py
import bcrypt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from typing import Optional
from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.db.database import get_db
from sqlalchemy.orm import Session
from app.models.tecnico import Tecnico

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# IMPORTANT: tokenUrl should NOT start with a leading slash when routers are mounted with prefix="/api"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # debug prints (ok for dev; remove in prod)
    # print("🔵 TOKEN RECEBIDO:", token)
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    return payload

async def get_current_active_user(current_payload: dict = Depends(get_current_user),
                                  db: Session = Depends(get_db)) -> dict:
    # The token should contain a 'user_id' (numeric id) — prefer numeric id in token for DB lookups
    user_id = current_payload.get("user_id")
    role = current_payload.get("role")

    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token sem user_id")

    # load technician from DB
    tecnico = db.query(Tecnico).filter(Tecnico.id_tecnico == user_id).first()
    if not tecnico or not getattr(tecnico, "is_active", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário inativo ou inexistente")

    # return normalized user object
    return {"user_id": tecnico.id_tecnico, "role": tecnico.role.value}

async def require_admin_role(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado: Requer privilégios de 'admin'.")
    return user

async def require_technician_role(user: dict = Depends(get_current_active_user)) -> dict:
    if user.get("role") != "tecnico":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado: Requer privilégios de 'tecnico'.")
    return user
