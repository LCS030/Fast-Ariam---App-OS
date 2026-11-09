from typing import Optional

from pydantic import BaseModel, Field


class MaterialBase(BaseModel):
    nome: str = Field(..., min_length=1, max_length=100)
    quantidade: int = Field(..., ge=0)
    valor: float = Field(..., ge=0)


class Material(MaterialBase):
    id_material: Optional[int] = None

    class Config:
        from_attributes = True
