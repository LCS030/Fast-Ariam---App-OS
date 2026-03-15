from pydantic import BaseModel
from typing import List, Optional
from .material import Material


class ServicoEquipamentoBase(BaseModel):
    numero_serie_atendido: str
    nome_equipamento: str
    defeitos_principais: List[str] = []
    defeito_outros_descricao: Optional[str] = None

    sub_defeitos_refrigeracao: List[str] = []
    sub_defeitos_compressor: List[str] = []
    sub_defeitos_vazamento: List[str] = []
    vazamento_ponto_descricao: Optional[str] = None

    sub_defeitos_outros: List[str] = []
    sub_defeitos_iluminacao: List[str] = []
    sub_defeitos_estrutura: List[str] = []

    materiais_utilizados: List[Material] = []


class ServicoEquipamento(ServicoEquipamentoBase):
    id_servico: int

    class Config:
        from_attributes = True
