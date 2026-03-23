from pydantic import BaseModel

class IniciarDeslocamentoPayload(BaseModel):
    tipo: str
    km_inicio: int