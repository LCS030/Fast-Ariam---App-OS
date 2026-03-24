from pydantic import BaseModel
from typing import Optional


class MaterialBase(BaseModel):
    nome: str
    quantidade: int
    valor: float


class Material(MaterialBase):
    id_material: Optional[int] = None

    class Config:
        from_attributes = True
