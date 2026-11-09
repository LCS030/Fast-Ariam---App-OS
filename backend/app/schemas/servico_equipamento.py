from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from .base_schemas import (PayloadComHorario, ServicoEquipamento, SubDefeitoCompressor, SubDefeitoEstrutura, SubDefeitoIluminacao,
                           SubDefeitoOutros, SubDefeitoRefrigeracao, SubDefeitoVazamento, TipoDefeitoPrincipal)
from .material import MaterialBase

# `ServicoEquipamento` (RESPOSTA) é definido em base_schemas e reexportado aqui: é o mesmo modelo usado em
# `Visita.servicos_realizados`. Inclui `id_os_equipamento`, `modelo`, `numero_serie` (somente leitura),
# `conserto_salvo_em` e `is_legado` (SDD 6.7.1).
__all__ = ["SalvarConsertoPayload", "ServicoEquipamento", "ServicoEquipamentoUpdate"]


class ServicoEquipamentoUpdate(BaseModel):
    """
    Corpo de PATCH .../servicos/{s}: parcial; apenas os campos enviados são alterados.

    v0.5 (RN-42): o técnico NÃO envia equipamento, modelo nem número de série. `extra = "forbid"` faz qualquer campo
    fora desta lista (inclusive `numero_serie_atendido`, `nome_equipamento` e `id_os_equipamento`) responder 422 em vez
    de ser ignorado em silêncio. O registro de serviço é criado pelo servidor (um por equipamento da OS na visita).
    """
    model_config = ConfigDict(extra="forbid")

    defeitos_principais: Optional[List[TipoDefeitoPrincipal]] = None
    defeito_outros_descricao: Optional[str] = None
    sub_defeitos_refrigeracao: Optional[List[SubDefeitoRefrigeracao]] = None
    sub_defeitos_compressor: Optional[List[SubDefeitoCompressor]] = None
    sub_defeitos_vazamento: Optional[List[SubDefeitoVazamento]] = None
    vazamento_ponto_descricao: Optional[str] = None
    sub_defeitos_outros: Optional[List[SubDefeitoOutros]] = None
    sub_defeitos_iluminacao: Optional[List[SubDefeitoIluminacao]] = None
    sub_defeitos_estrutura: Optional[List[SubDefeitoEstrutura]] = None
    materiais_utilizados: Optional[List[MaterialBase]] = None


class SalvarConsertoPayload(PayloadComHorario):
    """Corpo opcional de POST .../servicos/{s}/salvar-conserto: só `ocorrido_em` (ISO-8601 com fuso, SDD 6.6.4)."""
