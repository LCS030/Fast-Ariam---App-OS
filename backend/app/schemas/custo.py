from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel


class CustoMaterialDetalhado(BaseModel):
    nome: str
    quantidade: int
    valor_unitario: float
    valor_total: float


class CustoVisitaDetalhado(BaseModel):
    id_visita: int
    data: date
    custo_total_materiais: float
    custo_km: float
    custo_pedagio: float
    custo_frete: float
    custo_tempo_servico: float
    custo_tempo_deslocamento: float
    subtotal_visita: float

    class Config:
        from_attributes = True


class CustoTotalResponse(BaseModel):
    id_os: int
    custo_total_materiais: float
    custo_total_km: float
    custo_total_pedagio: float
    custo_total_frete: float
    custo_total_servico: float
    custo_total_deslocamento: float
    total_geral: float
    detalhes_por_visita: List[CustoVisitaDetalhado]
    detalhes_materiais_compilado: List[CustoMaterialDetalhado]
    # Acrescentados na v0.3: True quando o valor vem do snapshot imutável de `custo_os` (OS Finalizada).
    congelado: bool = False
    calculado_em: Optional[datetime] = None
    valores_utilizados: Optional[dict] = None
