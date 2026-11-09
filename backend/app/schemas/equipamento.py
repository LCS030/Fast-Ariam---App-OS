"""
Schemas do catálogo de modelos e dos equipamentos da OS (SDD 6.13, PRD 6.10).

O técnico NUNCA envia estes campos: catálogo e vínculo são do administrador (RN-42).
"""
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Modelo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NumeroSerie = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class EquipamentoModeloCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: Modelo = Field(..., examples=["Freezer vertical modelo X"])


class EquipamentoModeloUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    modelo: Optional[Modelo] = None
    is_active: Optional[bool] = None


class EquipamentoModelo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_equipamento_modelo: int
    modelo: str
    is_active: bool = True


class OsEquipamentoCreate(BaseModel):
    """Equipamento a vincular à OS: modelo ativo do catálogo + número de série."""
    id_equipamento_modelo: int = Field(..., gt=0)
    numero_serie: NumeroSerie


class OsEquipamentoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id_equipamento_modelo: Optional[int] = Field(None, gt=0)
    numero_serie: Optional[NumeroSerie] = None


class OsEquipamento(BaseModel):
    """Resposta: equipamento da OS (somente leitura para o técnico)."""
    model_config = ConfigDict(from_attributes=True)

    id_os_equipamento: int
    id_equipamento_modelo: int
    modelo: str
    numero_serie: str
