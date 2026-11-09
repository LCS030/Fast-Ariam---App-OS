from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field, StringConstraints, field_validator

from .base_schemas import StatusChamado
from .equipamento import OsEquipamento, OsEquipamentoCreate
from .visita import Visita


class ChamadoBase(BaseModel):
    id_cliente: int = Field(..., gt=0, description="ID do cliente associado ao chamado")
    descricao_cliente: str
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    pedido: Optional[str] = None
    data_faturamento: Optional[date] = None
    em_garantia: bool = True


class ChamadoCreate(ChamadoBase):
    """
    Entrada de criação (SDD 6.5.1). O status NÃO é informado: o servidor define `Pendente` (sem técnico) ou
    `Agendado` (com técnico ativo) - RN-10 / T-26. Campos extras (ex.: `status`) são ignorados.

    v0.5 (RN-41): `equipamentos` é OBRIGATÓRIO, com ao menos 1 item (modelo ativo do catálogo + número de série), e as
    séries não podem se repetir na lista (sem diferenciar maiúsculas). OS sem equipamento não é criada (422).
    """
    equipamentos: List[OsEquipamentoCreate] = Field(..., min_length=1)

    @field_validator("equipamentos")
    @classmethod
    def _series_unicas(cls, itens: List[OsEquipamentoCreate]) -> List[OsEquipamentoCreate]:
        vistas = set()
        for item in itens:
            chave = item.numero_serie.upper()
            if chave in vistas:
                raise ValueError(f"Número de série repetido na lista de equipamentos: '{item.numero_serie}'.")
            vistas.add(chave)
        return itens


class Chamado(BaseModel):
    """Resposta de OS. Tolerante a dados legados (descricao_cliente pode ser nula no banco)."""
    id_os: int
    id_cliente: int
    descricao_cliente: Optional[str] = None
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    pedido: Optional[str] = None
    data_faturamento: Optional[date] = None
    em_garantia: bool = True
    data_conclusao: Optional[date] = None
    data_abertura: date
    status: StatusChamado
    is_cancelled: bool = False
    motivo_cancelamento: Optional[str] = None
    cancelado_em: Optional[datetime] = None
    cancelado_por: Optional[int] = None
    # DESCONTINUADO (PR-35): a assinatura é da visita. Mantido só para dados antigos.
    assinatura_cliente_url: Optional[str] = Field(
        None, description="Descontinuado: use visitas[].assinatura_url.")
    cliente_nome: Optional[str] = None
    equipamentos: List[OsEquipamento] = Field(default_factory=list)
    visitas: List[Visita] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ChamadoUpdate(BaseModel):
    """
    PATCH administrativo (SDD 6.5). `status` só é aceito quando coincide com a transição implícita da atribuição;
    `Finalizado` nunca (403). `is_cancelled`/`data_conclusao` são rejeitados pelo handler (use POST /cancelar).
    """
    id_cliente: Optional[int] = Field(None, gt=0, description="Novo ID do cliente para reassociar o chamado")
    descricao_cliente: Optional[str] = None
    id_tecnico_atribuido: Optional[int] = None
    data_agendamento: Optional[date] = None
    pedido: Optional[str] = None
    data_faturamento: Optional[date] = None
    em_garantia: Optional[bool] = None
    status: Optional[StatusChamado] = None
    is_cancelled: Optional[bool] = None
    data_conclusao: Optional[date] = None


class CancelarChamadoPayload(BaseModel):
    """Corpo de POST /{id}/cancelar: motivo obrigatório, não vazio, até 500 caracteres (SDD 6.9)."""
    motivo: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class ReagendarPayload(BaseModel):
    """Corpo de POST /{id}/reagendar (SDD 6.10)."""
    data_visita: date
