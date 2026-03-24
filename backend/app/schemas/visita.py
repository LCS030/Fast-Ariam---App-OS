from pydantic import BaseModel, Field, model_validator, field_validator
from datetime import date
from typing import List, Optional
from .base_schemas import ServicoEquipamento


# noinspection PyArgumentList
class VisitaBase(BaseModel):
    """
    Schema base para uma visita técnica.
    Captura os dados brutos para o cálculo de custos.
    """
    data_visita: date = Field(..., example="2025-10-21")
    hora_inicio_deslocamento: str = Field(..., example="08:00")
    hora_chegada_cliente: str = Field(..., example="09:15")
    hora_inicio_atendimento: str = Field(..., example="09:30")
    hora_fim_atendimento: str = Field(..., example="11:00")
    km_total: int = Field(..., gt=0, description="Total de KMs rodados (ida + volta).", example=55)
    valor_pedagio: float = Field(0.0, ge=0, description="Custo total de pedágios na rota.", example=9.80)
    valor_frete_devolucao: float = Field(0.0, ge=0, description="Custo de frete para devolução de peças.",
                                         example=16.35)
    descricao_servico_executado: str = Field(..., description="Descrição do serviço executado e observações.",
                                             example="Troca do filtro secador e reoperação de vácuo.")
    servico_finalizado: bool = Field(False,
                                     description="O serviço foi finalizado? Falso na criação. Usar PATCH para finalizar.")
    pendencia: Optional[str] = Field(None, description="Se o serviço não foi finalizado, qual a pendência?",
                                     example="Aguardando peça X.")
    nome_ajudante: Optional[str] = Field(None, example="Carlos Silva", description="Nome do ajudante, se houver.")
    telefone_ajudante: Optional[str] = Field(None, example="27998887766",
                                             description="Telefone do ajudante, se houver.")
    servicos_realizados: List[ServicoEquipamento] = Field(...,
                                                          description="Lista de trabalhos realizados em cada equipamento")


@model_validator(mode='after')
def check_finalizacao_na_criacao(self) -> 'VisitaBase':
    if self.servico_finalizado is True:
        raise ValueError("Não é possível criar uma visita já finalizada. Finalize via PATCH após os uploads.")
    return self


class VisitaCreate(VisitaBase):
    """
    Schema de entrada de uma visita.
    """
    pass


class Visita(VisitaBase):
    """
    Schema de saída de uma visita.
    """
    id_visita: int
    odometro_inicio_url: Optional[str] = Field(None, description="URL da foto do odômetro no início do deslocamento.")
    odometro_fim_url: Optional[str] = Field(None, description="URL da foto do odômetro no fim do deslocamento.")
    comprovante_pedagio_urls: List[str] = Field(default_factory=list,
                                                description="Lista de URLs dos comprovantes de pedágio.")
    comprovante_frete_urls: List[str] = Field(default_factory=list,
                                              description="Lista de URLs dos comprovantes de frete para devolução de peças.")
    assinatura_cliente_url: Optional[str] = Field(None, description="URL da imagem da assinatura digital do cliente.")

    class Config:
        from_attributes = True


# TODO: Tratar futuramente o PEDÁGIO para ter comprovante para reembolso
# TODO: Tratar futuramente Controlador, compressor, fonte e micromotor são devolvidos à Fast, para fazer o reembolso do frete é preciso ter o comprovante

class VisitaUpdate(BaseModel):
    """
    Schema para atualizar uma visita, possibilitando editar e/ou adicionar informações e URLs de arquivos pós-upload.
    Todos os campos são opcionais.
    """
    data_visita: Optional[date] = None
    hora_saida_empresa: Optional[str] = None
    hora_chegada_cliente: Optional[str] = None
    hora_inicio_servico: Optional[str] = None
    hora_fim_servico: Optional[str] = None
    km_total: Optional[int] = None
    valor_pedagio: Optional[float] = None
    valor_frete_devolucao: Optional[float] = None
    descricao_tecnico: Optional[str] = None
    servicos_realizados: Optional[List[ServicoEquipamento]] = None
    servico_finalizado: Optional[bool] = None
    pendencia: Optional[str] = None
    nome_ajudante: Optional[str] = None
    telefone_ajudante: Optional[str] = None
    odometro_inicio_url: Optional[str] = None
    odometro_fim_url: Optional[str] = None
    comprovante_pedagio_urls: Optional[List[str]] = None
    comprovante_frete_urls: Optional[List[str]] = None
    assinatura_cliente_url: Optional[str] = None


    @field_validator('comprovante_pedagio_urls', 'comprovante_frete_urls', mode='before')
    @classmethod
    def convert_none_to_empty_list(cls, v):
        """Se o valor vindo do DB for None, converte para lista vazia."""
        if v is None:
            return []
        return v
