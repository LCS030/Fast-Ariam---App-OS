from sqlalchemy import Column, Integer, String, Boolean, Date, Text, ForeignKey, Numeric, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base


class Visita(Base):
    __tablename__ = "visita"

    id_visita = Column(Integer, primary_key=True, autoincrement=True)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"), nullable=False)

    data_visita = Column(Date, nullable=False)

    hora_inicio_deslocamento = Column(String(5))
    hora_chegada_cliente = Column(String(5))
    hora_inicio_atendimento = Column(String(5), nullable=True)
    hora_fim_atendimento = Column(String(5), nullable=True)

    km_total = Column(Integer, nullable=False, default=0)

    valor_pedagio = Column(Numeric(10, 2), nullable=False, default=0.00)
    valor_frete_devolucao = Column(Numeric(10, 2), nullable=False, default=0.00)

    descricao_servico_executado = Column(Text)

    nome_ajudante = Column(String(100))
    telefone_ajudante = Column(String(20))

    servico_finalizado = Column(Boolean, nullable=False, default=False)
    pendencia = Column(Text)

    odometro_inicio_url = Column(String(255))
    odometro_fim_url = Column(String(255))
    assinatura_cliente_url = Column(String(255))

    comprovante_pedagio_urls = Column(JSON, nullable=False, server_default="[]")
    comprovante_frete_urls = Column(JSON, nullable=False, server_default="[]")

    # ======================
    # CAMPOS DE IDA
    # ======================
    km_inicio_ida = Column(Integer)
    km_fim_ida = Column(Integer)
    hora_inicio_ida = Column(String(5))
    hora_fim_ida = Column(String(5))
    foto_inicio_ida_url = Column(String(255))
    foto_fim_ida_url = Column(String(255))

    # ======================
    # CAMPOS DE VOLTA
    # ======================
    km_inicio_volta = Column(Integer)
    km_fim_volta = Column(Integer)
    hora_inicio_volta = Column(String(5))
    hora_fim_volta = Column(String(5))
    foto_inicio_volta_url = Column(String(255))
    foto_fim_volta_url = Column(String(255))

    nome_cliente = Column(String(100))
    documento_cliente = Column(String(30))

    ordem_servico = relationship("OrdemServico", back_populates="visitas")
    servicos_realizados = relationship(
        "ServicoEquipamento",
        back_populates="visita",
        cascade="all, delete-orphan",
    )
