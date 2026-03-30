from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ServicoFotoResponse(BaseModel):
    """Schema para resposta de foto de serviço."""
    id_foto: int
    id_servico: int
    tipo: str  # 'defeito' ou 'conserto'
    url: str
    
    class Config:
        from_attributes = True


class ServicoFotoListResponse(BaseModel):
    """Schema para listar fotos de um serviço."""
    fotos_defeito: list[ServicoFotoResponse]
    fotos_conserto: list[ServicoFotoResponse]
    
    class Config:
        from_attributes = True


class UploadFotoResponse(BaseModel):
    """Schema para resposta de upload de foto."""
    status: str
    url: str
    tipo: str
    id_foto: Optional[int] = None
