from pydantic import BaseModel, Field, field_validator

# bcrypt só considera os 72 primeiros bytes (e a lib 5.x recusa mais que isso).
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


def validar_forca_senha(valor: str) -> str:
    """Política mínima de senha: 8 caracteres e no máximo 72 bytes (limite do bcrypt). Sem truncar silenciosamente."""
    if len(valor) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"A senha deve ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
    if len(valor.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(f"A senha deve ter no máximo {MAX_PASSWORD_BYTES} bytes.")
    if not valor.strip():
        raise ValueError("A senha não pode ser composta apenas por espaços.")
    return valor


class Token(BaseModel):
    access_token: str
    token_type: str


class PasswordUpdate(BaseModel):
    """
    Schema para o corpo da requisição de atualização de senha (PATCH /api/tecnicos/me/password).
    """
    old_password: str = Field(..., description="Senha atual do usuário logado.")
    new_password: str = Field(..., description="Nova senha (mínimo 8 caracteres, máximo 72 bytes).")

    @field_validator("new_password")
    @classmethod
    def _senha_nova_valida(cls, valor: str) -> str:
        return validar_forca_senha(valor)
