from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class Material(BaseModel):
    """A estrutura para a declaração do uso de um material no chamado."""
    nome: str
    quantidade: int
    valor: float

    class Config:
        from_attributes = True


class UserRole(str, Enum):
    """Define os papéis de usuário permitidos no sistema."""
    ADMIN = "admin"
    TECNICO = "tecnico"


class StatusChamado(str, Enum):
    ABERTO = "Aberto"
    AGENDADO = "Agendado"
    EM_ATENDIMENTO = "Em Atendimento"
    PENDENTE = "Pendente"
    FINALIZADO = "Finalizado"


class TipoDefeitoPrincipal(str, Enum):
    """Categorias principais de defeito."""
    REFRIGERACAO = "Refrigeração"
    ILUMINACAO = "Iluminação"
    ESTRUTURA = "Estrutura"
    OUTROS = "Outros"


class SubDefeitoRefrigeracao(str, Enum):
    """Sub-categorias para defeitos de Refrigeração."""
    COMPRESSOR = "Compressor"
    VAZAMENTO = "Vazamento"
    OUTROS = "Outros (Refrigeração)"


class SubDefeitoCompressor(str, Enum):
    """Sub-categorias para defeitos de Compressão."""
    QUEIMADO = "Queimado"
    EM_MASSA = "Em Massa"
    EM_CURTO = "Em Curto"
    CORRENTE_ALTA = "Corrente Alta"
    NAO_PARTE = "Não Parte"
    SEM_COMPRESSAO = "Sem Compressão"
    TRAVADO = "Travado"
    COM_BARULHO = "Com Barulho"
    NAO_SUCCIONA = "Não Succiona"
    DESARMADO = "Desarmado"


class SubDefeitoVazamento(str, Enum):
    """Sub-categorias para defeitos de Vazamento."""
    N_PONTO = "Nº Ponto"
    NAO_LOCALIZADO = "Não Localizado"


class SubDefeitoOutros(str, Enum):
    """Sub-categorias para Outros defeitos."""
    FILTRO_ENTUPIDO = "Filtro Entupido"
    CAPILAR_OBSTRUIDO = "Capilar Obstruído"
    MICROMOTOR_QUEIMADO = "Micromotor Queimado"
    MICROMOTOR_TRAVADO = "Micromotor Travado"
    CONTROLADOR_QUEIMADO = "Controlador Queimado"
    REGULAGEM_PARAMETROS = "Regulagem Parâmetros"


class SubDefeitoIluminacao(str, Enum):
    """Sub-categorias para defeitos de Iluminação."""
    LAMPADA_QUEIMADA = "Lâmpada Queimada"
    SEM_ALIMENTACAO = "Sem Alimentação"
    EM_CURTO = "Em Curto"


class SubDefeitoEstrutura(str, Enum):
    """Sub-categorias para defeitos de Estrutura."""
    PERFIL_CURVO_VIDRO = "01 - Perfil Curvo Vidro"
    PERFIL_SUPORTE_ILUMINACAO = "02 - Perfil Suporte Iluminação"
    LENTE_CALHA_ILUMINACAO = "03 - Lente Calha Iluminação"
    PERFIL_VEDACAO = "04 - Perfil Vedação"
    PERFIL_PORTA_ETIQUETA = "05 - Perfil Porta Etiqueta"
    PUXADOR = "06 - Puxador"
    PORTA_PARACHOQUE = "07 - Porta Parachoque"
    CANTO_90 = "08 - Canto 90°"
    ACRILICO_CAREL = "09 - Acrílico Carel"
    PERFIL_FRONTAL = "10 - Perfil Frontal"
    PARACHOQUE_FRONTAL = "11 - Parachoque Frontal"
    PARACHOQUE_LATERAL = "12 - Parachoque Lateral"


# noinspection PyArgumentList
class ServicoEquipamento(BaseModel):
    """Representa um trabalho realizado em um único equipamento durante uma visita."""
    numero_serie_atendido: str = Field(..., description="Numero de série do equipamento atendido.")
    defeitos_principais: List[TipoDefeitoPrincipal] = Field(default_factory=list,
                                                            description="Lista de categorias principais do defeito.")
    defeito_outros_descricao: Optional[str] = Field(None,
                                                    description="Descrição se 'Outros' for selecionado em defeitos_principais")
    sub_defeitos_refrigeracao: List[SubDefeitoRefrigeracao] = Field(default_factory=list,
                                                                    description="Sub-defeitos de Refrigeração")
    sub_defeitos_compressor: List[SubDefeitoCompressor] = Field(default_factory=list,
                                                                description="Detalhes do defeito de Compressor")
    sub_defeitos_vazamento: List[SubDefeitoVazamento] = Field(default_factory=list,
                                                              description="Detalhes do defeito de Vazamento")
    vazamento_ponto_descricao: Optional[str] = Field(None,
                                                     description="Descrição por extenso dos pontos de vazamento")
    sub_defeitos_outros: List[SubDefeitoOutros] = Field(default_factory=list,
                                                        description="Detalhes de 'Outros' em Refrigeração")
    sub_defeitos_iluminacao: List[SubDefeitoIluminacao] = Field(default_factory=list,
                                                                description="Detalhes do defeito de Iluminação")
    sub_defeitos_estrutura: List[SubDefeitoEstrutura] = Field(default_factory=list,
                                                              description="Detalhes do defeito de Estrutura")

    materiais_utilizados: List[Material] = Field(
        example=[
            {"nome": "Filtro Secador XYZ", "quantidade": 1, "valor": 85.00},
            {"nome": "Gás R-134a", "quantidade": 2, "valor": 50.00}
        ]
    )

    class Config:
        from_attributes = True
