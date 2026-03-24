from pydantic import BaseModel, Field
from datetime import date
from typing import Optional, List
from .visita import Visita
from .base_schemas import StatusChamado


class ChamadoBase(BaseModel):
    id_cliente: int = Field(..., gt=0, description="ID do cliente associado ao chamado") # TODO: Lembrar de continuar a validação
    descricao_cliente: str
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    pedido: Optional[str] = None
    data_faturamento: Optional[date] = None
    em_garantia: bool = True
    data_conclusao: Optional[date] = None
    status: StatusChamado = StatusChamado.ABERTO


class ChamadoCreate(ChamadoBase):
    pass


class Chamado(ChamadoBase):
    id_os: int
    data_abertura: date
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    visitas: List[Visita] = Field(default_factory=list)
    is_cancelled: bool = False

    class Config:
        from_attributes = True


class ChamadoUpdate(BaseModel):
    id_cliente: Optional[int] = Field(None, gt=0, description="Novo ID do cliente para reassociar o chamado")
    descricao_cliente: Optional[str] = None
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    status: Optional[StatusChamado] = None
    is_cancelled: Optional[bool] = None
    data_conclusao: Optional[date] = None
