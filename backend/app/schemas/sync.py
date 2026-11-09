"""Schemas da sincronização offline (SDD 6.12)."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_EVENTOS_POR_LOTE = 200


def _exigir_fuso(v: datetime) -> datetime:
    if v.tzinfo is None or v.utcoffset() is None:
        raise ValueError("Informe o horário COM fuso (ex.: 2026-11-09T14:02:11-03:00).")
    return v


class EventoSync(BaseModel):
    client_event_id: UUID
    tipo: str = Field(..., min_length=1, max_length=50)
    id_os: int = Field(..., gt=0)
    id_visita: int = Field(..., gt=0)
    ocorrido_em: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)

    _fuso = field_validator("ocorrido_em")(_exigir_fuso)


class LoteSync(BaseModel):
    dispositivo_id: str = Field(..., min_length=1, max_length=64)
    enviado_em: datetime
    eventos: List[EventoSync] = Field(..., max_length=MAX_EVENTOS_POR_LOTE)

    _fuso = field_validator("enviado_em")(_exigir_fuso)


class ResultadoEvento(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    client_event_id: UUID
    resultado: str  # aplicado | duplicado | rejeitado
    codigo: Optional[str] = None
    detalhe: Optional[str] = None


class RespostaLote(BaseModel):
    resultados: List[ResultadoEvento]


class RespostaArquivo(BaseModel):
    client_file_id: UUID
    url: str
    resultado: str  # aplicado | duplicado
