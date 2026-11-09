from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
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
    """Status da OS (SDD 4.3). `Aberto` e LEGADO: so leitura, nenhuma operacao nova pode grava-lo (TR-09)."""
    ABERTO = "Aberto"
    AGENDADO = "Agendado"
    EM_ATENDIMENTO = "Em Atendimento"
    PENDENTE = "Pendente"
    FINALIZADO = "Finalizado"
    PAUSADO = "Pausado"
    AGUARDANDO_REAGENDAMENTO = "Aguardando Reagendamento"


class MotivoPausa(str, Enum):
    """Lista oficial de motivos de pausa (PRD RN-29 / SDD seção 7). App, painel e backend usam a mesma lista."""
    PECA_PENDENTE = "Peça pendente"
    CLIENTE_AUSENTE = "Cliente ausente"
    CONDICOES_INSEGURAS = "Condições inseguras"
    AGUARDANDO_APROVACAO = "Aguardando aprovação"
    OUTRO = "Outro"


# Tolerância para relógio do aparelho adiantado em relação ao servidor (AR-05).
TOLERANCIA_FUTURO = timedelta(minutes=5)


class PayloadComHorario(BaseModel):
    """
    Base dos payloads de ações que carimbam horário (AR-05 / RN-24 / PR-30).
    `ocorrido_em` e opcional: ISO-8601 COM fuso (ex.: 2026-10-29T14:02:11-03:00), vindo do aparelho.
    Sem ele, o servidor usa o instante atual (UTC). Futuro além de 5 minutos e rejeitado.
    """
    ocorrido_em: Optional[datetime] = Field(
        None, description="Momento real da ação no aparelho (ISO-8601 com fuso). Opcional.")

    @field_validator("ocorrido_em")
    @classmethod
    def _validar_ocorrido_em(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("ocorrido_em deve incluir o fuso horário (ex.: 2026-10-29T14:02:11-03:00).")
        adiantamento = v - datetime.now(timezone.utc)
        if adiantamento > TOLERANCIA_FUTURO:
            minutos = int(adiantamento.total_seconds() // 60)
            raise ValueError(
                f"ocorrido_em está {minutos} minutos no futuro (tolerância: 5 minutos). "
                "Verifique o relógio e o fuso do aparelho e tente novamente.")
        return v


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
    id_servico: int = Field(..., description="ID único do serviço realizado no equipamento")
    # v0.5: o equipamento vem da OS. `modelo` e `numero_serie` são SOMENTE LEITURA (vêm do vínculo da OS; em serviços
    # legados, do texto digitado na época). `numero_serie_atendido`/`nome_equipamento` são colunas legadas.
    id_os_equipamento: Optional[int] = Field(None, description="Equipamento da OS ao qual o serviço se refere.")
    modelo: Optional[str] = Field(None, description="Modelo do equipamento (somente leitura).")
    numero_serie: Optional[str] = Field(None, description="Número de série do equipamento (somente leitura).")
    conserto_salvo_em: Optional[datetime] = Field(None, description="Quando o técnico salvou o conserto (RN-47).")
    is_legado: bool = Field(False, description="True em serviços anteriores à v0.5, sem vínculo com a OS.")
    numero_serie_atendido: Optional[str] = Field(None, description="LEGADO: série digitada pelo técnico antes da v0.5.")
    nome_equipamento: Optional[str] = Field(None, description="LEGADO: nome digitado pelo técnico antes da v0.5.")
    # Resposta tolerante: listas de texto (os rótulos válidos são validados na ENTRADA, schemas/servico_equipamento.py).
    # Assim um valor legado/inesperado no banco nunca derruba a leitura da OS com 500.
    defeitos_principais: List[str] = Field(default_factory=list, description="Categorias principais do defeito.")
    defeito_outros_descricao: Optional[str] = Field(None,
                                                    description="Descrição se 'Outros' for selecionado em defeitos_principais")
    sub_defeitos_refrigeracao: List[str] = Field(default_factory=list, description="Sub-defeitos de Refrigeração")
    sub_defeitos_compressor: List[str] = Field(default_factory=list, description="Detalhes do defeito de Compressor")
    sub_defeitos_vazamento: List[str] = Field(default_factory=list, description="Detalhes do defeito de Vazamento")
    vazamento_ponto_descricao: Optional[str] = Field(None,
                                                     description="Descrição por extenso dos pontos de vazamento")
    sub_defeitos_outros: List[str] = Field(default_factory=list, description="Detalhes de 'Outros' em Refrigeração")
    sub_defeitos_iluminacao: List[str] = Field(default_factory=list, description="Detalhes do defeito de Iluminação")
    sub_defeitos_estrutura: List[str] = Field(default_factory=list, description="Detalhes do defeito de Estrutura")

    materiais_utilizados: List[Material] = Field(default_factory=list)
    fotos_defeito: List[str] = []
    fotos_conserto: List[str] = []

    class Config:
        from_attributes = True
