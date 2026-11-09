from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Text, ForeignKey, Numeric, DateTime, CheckConstraint, text,
)
from sqlalchemy.orm import relationship
from app.db.database import Base


class Visita(Base):
    __tablename__ = "visita"
    __table_args__ = (
        # SDD 4.7: CPF somente digitos (a validacao dos digitos verificadores e do backend).
        CheckConstraint("documento_cliente IS NULL OR documento_cliente ~ '^[0-9]{11}$'",
                        name="ck_visita_documento_cliente"),
    )

    id_visita = Column(Integer, primary_key=True, autoincrement=True)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"), nullable=False)
    data_visita = Column(Date, nullable=False)

    # --- LEGADO: horarios HH:mm (VARCHAR(5)). Derivados dos *_em abaixo ate os fronts migrarem. Nao ampliar uso. ---
    hora_inicio_deslocamento = Column(String(5))
    hora_chegada_cliente = Column(String(5))
    hora_inicio_atendimento = Column(String(5))
    hora_fim_atendimento = Column(String(5))
    # SDD 4.4: NOT NULL DEFAULT 0. Calculado: (km_fim_ida - km_inicio_ida) + (km_fim_volta - km_inicio_volta).
    km_total = Column(Integer, nullable=False, default=0, server_default=text("0"))
    # Campos para rastreamento de deslocamento IDA
    km_inicio_ida = Column(Integer)
    hora_inicio_ida = Column(String(5))   # legado
    km_fim_ida = Column(Integer)
    hora_fim_ida = Column(String(5))      # legado
    # Campos para rastreamento de deslocamento VOLTA
    km_inicio_volta = Column(Integer)
    hora_inicio_volta = Column(String(5))  # legado
    km_fim_volta = Column(Integer)
    hora_fim_volta = Column(String(5))     # legado

    # --- Novos (SDD 4.7): momento real da acao, vindo do aparelho, com fuso (TIMESTAMPTZ) ---
    ida_inicio_em = Column(DateTime(timezone=True))
    ida_fim_em = Column(DateTime(timezone=True))
    atendimento_inicio_em = Column(DateTime(timezone=True))
    atendimento_fim_em = Column(DateTime(timezone=True))
    volta_inicio_em = Column(DateTime(timezone=True))
    volta_fim_em = Column(DateTime(timezone=True))

    valor_pedagio = Column(Numeric(10, 2), nullable=False, default=0.00, server_default=text("0"))
    valor_frete_devolucao = Column(Numeric(10, 2), nullable=False, default=0.00, server_default=text("0"))
    descricao_servico_executado = Column(Text)
    # LEGADO: ajudantes estao fora do escopo v0.3. Colunas mantidas so para historico; sem uso/tela/calculo.
    nome_ajudante = Column(String(100))
    telefone_ajudante = Column(String(20))
    servico_finalizado = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    pendencia = Column(Text)
    odometro_inicio_url = Column(String(255))
    odometro_fim_url = Column(String(255))
    # URLs das fotos de deslocamento (ida e volta, inicio e fim) - referencia/path do objeto no Storage
    foto_inicio_ida_url = Column(String(255))
    foto_fim_ida_url = Column(String(255))
    foto_inicio_volta_url = Column(String(255))
    foto_fim_volta_url = Column(String(255))

    # --- Assinatura do cliente na visita (SDD 4.7, PR-10, PR-35) ---
    assinatura_url = Column(String(255))            # caminho no Storage
    nome_cliente_assinatura = Column(String(100))   # quem assinou
    documento_cliente = Column(String(11))          # CPF, so digitos

    comprovantes = relationship("Comprovante", back_populates="visita", cascade="all, delete-orphan")
    ordem_servico = relationship("OrdemServico", back_populates="visitas")
    servicos_realizados = relationship("ServicoEquipamento", back_populates="visita", cascade="all, delete-orphan")

    @property
    def comprovante_pedagio_urls(self):
        return [c.url for c in self.comprovantes if c.tipo == 'pedagio']

    @property
    def comprovante_frete_urls(self):
        return [c.url for c in self.comprovantes if c.tipo == 'frete']
