from pydantic import BaseModel
from typing import List
from datetime import date

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