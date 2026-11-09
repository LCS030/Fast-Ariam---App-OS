from datetime import date, datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from .base_schemas import MotivoPausa, PayloadComHorario, ServicoEquipamento


# ---------------------------------------------------------------------------------------------------------------------
# Unificação VisitaBase / VisitaCreate / VisitaUpdate (SDD seção 7, linha "Visita km_total"):
#   * VisitaBase    -> campos de ENTRADA comuns (o que o admin/técnico informa).
#   * VisitaCreate  -> VisitaBase + servico_finalizado (deve ser false; o handler responde 400 se vier true).
#   * VisitaUpdate  -> parcial, apenas campos editáveis. Horários, km, assinatura e finalização NUNCA são editáveis por
#                      PATCH: são gravados pelas ações do fluxo (iniciar/finalizar deslocamento, atendimento etc.).
#   * Visita        -> RESPOSTA, tolerante: horários opcionais e km_total >= 0 (PR-11 / T-10).
# `km_total` deixou de ser entrada: o servidor calcula
#   (km_fim_ida - km_inicio_ida) + (km_fim_volta - km_inicio_volta) ao finalizar o deslocamento (SDD 4.7).
# Ajudantes (RN-25) não existem nos schemas de entrada; permanecem apenas na resposta, como histórico legado.
# ---------------------------------------------------------------------------------------------------------------------


class VisitaBase(BaseModel):
    data_visita: date = Field(..., examples=["2026-11-05"])
    descricao_servico_executado: Optional[str] = Field(
        None, description="Descrição do serviço executado e observações.")
    valor_pedagio: float = Field(0.0, ge=0, description="Custo total de pedágios na rota.")
    valor_frete_devolucao: float = Field(0.0, ge=0, description="Custo de frete para devolução de peças.")
    pendencia: Optional[str] = Field(None, description="Pendência do serviço, em texto livre (não altera o status da OS).")


class VisitaCreate(VisitaBase):
    """Entrada de criação. A visita nasce vazia; tudo o mais é preenchido pelo fluxo."""
    servico_finalizado: bool = Field(False, description="Deve ser false na criação (a visita finaliza na volta).")


class VisitaUpdate(BaseModel):
    """PATCH parcial. Só os campos abaixo são aceitos; os demais são ignorados."""
    data_visita: Optional[date] = None
    descricao_servico_executado: Optional[str] = None
    valor_pedagio: Optional[float] = Field(None, ge=0)
    valor_frete_devolucao: Optional[float] = Field(None, ge=0)
    pendencia: Optional[str] = None
    # Mantido só para devolver 400 claro: a visita NÃO finaliza por PATCH (TR-02 / SDD 6.6).
    servico_finalizado: Optional[bool] = None


class PausaResponse(BaseModel):
    """Pausa da visita (D5): a lista completa permite ao painel mostrar histórico e autor."""
    model_config = ConfigDict(from_attributes=True)

    id_pausa: int
    visita_id: int
    motivo: str
    descricao: Optional[str] = None
    criado_em: Optional[datetime] = None
    encerrada_em: Optional[datetime] = None
    is_ativa: bool = True
    por_usuario_id: Optional[int] = None
    por_papel: Optional[str] = None


class Visita(BaseModel):
    """Resposta de uma visita. Tolerante a visitas incompletas (PR-11)."""
    model_config = ConfigDict(from_attributes=True)

    id_visita: int
    id_os: Optional[int] = None
    data_visita: date

    # Momentos reais (TIMESTAMPTZ) - fonte de verdade (AR-05)
    ida_inicio_em: Optional[datetime] = None
    ida_fim_em: Optional[datetime] = None
    atendimento_inicio_em: Optional[datetime] = None
    atendimento_fim_em: Optional[datetime] = None
    volta_inicio_em: Optional[datetime] = None
    volta_fim_em: Optional[datetime] = None

    # LEGADO HH:mm derivado dos *_em (para os fronts atuais)
    hora_inicio_deslocamento: Optional[str] = None
    hora_chegada_cliente: Optional[str] = None
    hora_inicio_atendimento: Optional[str] = None
    hora_fim_atendimento: Optional[str] = None
    hora_inicio_ida: Optional[str] = None
    hora_fim_ida: Optional[str] = None
    hora_inicio_volta: Optional[str] = None
    hora_fim_volta: Optional[str] = None

    km_total: int = Field(0, ge=0, description="Calculado pelo servidor: (fim_ida - inicio_ida) + (fim_volta - inicio_volta).")
    km_inicio_ida: Optional[int] = None
    km_fim_ida: Optional[int] = None
    km_inicio_volta: Optional[int] = None
    km_fim_volta: Optional[int] = None

    valor_pedagio: float = Field(0.0, ge=0)
    valor_frete_devolucao: float = Field(0.0, ge=0)
    descricao_servico_executado: Optional[str] = None
    servico_finalizado: bool = False
    pendencia: Optional[str] = None

    # Legado (RN-25): apenas histórico, sem uso em novas operações.
    nome_ajudante: Optional[str] = None
    telefone_ajudante: Optional[str] = None

    odometro_inicio_url: Optional[str] = None
    odometro_fim_url: Optional[str] = None
    foto_inicio_ida_url: Optional[str] = None
    foto_fim_ida_url: Optional[str] = None
    foto_inicio_volta_url: Optional[str] = None
    foto_fim_volta_url: Optional[str] = None
    comprovante_pedagio_urls: List[str] = Field(default_factory=list)
    comprovante_frete_urls: List[str] = Field(default_factory=list)

    # Assinatura do cliente pertence à visita (PR-10 / PR-35)
    assinatura_url: Optional[str] = None
    nome_cliente_assinatura: Optional[str] = None
    documento_cliente: Optional[str] = None

    servicos_realizados: List[ServicoEquipamento] = Field(default_factory=list)
    pausas: List[PausaResponse] = Field(default_factory=list)

    @field_validator("pausas", mode="before")
    @classmethod
    def _pausas_em_ordem(cls, v):
        return sorted(v, key=lambda p: getattr(p, "id_pausa", None) or p.get("id_pausa", 0)) if v else []


# ---------------------------------------------------------------------------------------------------------------------
# Payloads de ações da visita
# ---------------------------------------------------------------------------------------------------------------------

class IniciarAtendimentoPayload(PayloadComHorario):
    """Corpo opcional de iniciar-atendimento: só `ocorrido_em`."""


class PausarPayload(PayloadComHorario):
    """Pausar (SDD 6.6.2). `motivo` fora da lista -> 422; "Outro" exige `descricao` -> 422 (RN-29)."""
    motivo: MotivoPausa
    descricao: Optional[str] = None

    @model_validator(mode="after")
    def _outro_exige_descricao(self) -> "PausarPayload":
        if self.descricao is not None:
            self.descricao = self.descricao.strip() or None
        if self.motivo == MotivoPausa.OUTRO and not self.descricao:
            raise ValueError('A descrição é obrigatória quando o motivo é "Outro".')
        return self


class FinalizarAtendimentoPayload(PayloadComHorario):
    """Finalizar atendimento (SDD 6.6): nome, CPF e assinatura ficam NA VISITA (RN-22 / RN-23)."""
    nome_cliente: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    documento_cliente: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    assinatura_base64: str = Field(..., min_length=1)
