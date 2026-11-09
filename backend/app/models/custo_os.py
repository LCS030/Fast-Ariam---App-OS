from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, JSON, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from app.db.database import Base

# JSONB no PostgreSQL; JSON generico nos demais dialetos (ex.: SQLite em testes locais).
JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


class CustoOS(Base):
    """
    Snapshot do custo calculado na finalizacao da OS (SDD 4.7, 6.11). Uma linha por OS (PK = FK id_os).
    Guarda total, detalhamento e copia dos valores globais usados: nao muda quando a configuracao muda.
    Imutabilidade (Q11) e regra de aplicacao; o banco nao bloqueia UPDATE nesta versao.
    """
    __tablename__ = "custo_os"
    __table_args__ = (
        CheckConstraint("total >= 0", name="ck_custo_os_total_nao_negativo"),
    )

    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"), primary_key=True, autoincrement=False)
    calculado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    total = Column(Numeric(12, 2), nullable=False)
    detalhes = Column(JSONB_COMPAT, nullable=False)
    valores_utilizados = Column(JSONB_COMPAT, nullable=False)

    ordem_servico = relationship("OrdemServico", backref=backref("custo", uselist=False))
