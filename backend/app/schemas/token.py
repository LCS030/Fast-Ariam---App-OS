from pydantic import BaseModel

class Token(BaseModel):
    access_token: str
    token_type: str

class PasswordUpdate(BaseModel):
    """
    Schema para o corpo da requisição de atualização de senha.
    """
    old_password: str
    new_password: str