from typing import Literal

from pydantic import Field

from .base_schemas import PayloadComHorario


class IniciarDeslocamentoPayload(PayloadComHorario):
    tipo: Literal["ida", "volta"]
    km_inicio: int = Field(..., ge=0)


class FinalizarDeslocamentoPayload(PayloadComHorario):
    tipo: Literal["ida", "volta"]
    km_fim: int = Field(..., ge=0)
