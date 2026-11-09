from sqlalchemy import Column, SmallInteger, Numeric, DateTime, CheckConstraint, text
from sqlalchemy.sql import func
from app.db.database import Base


class ConfiguracaoCusto(Base):
    """
    Configuracao GLOBAL de custo (SDD 4.7 / PRD v0.3): linha unica (id_configuracao = 1), sem FK para tecnico.
    Tecnico nao edita. O custo e interno, nao cobrado do cliente.
    A linha NAO e semeada pela migracao (nao ha valores aprovados): o Backend deve tratar ausencia como
    'nao configurado' ou fazer upsert na primeira gravacao do admin.
    """
    __tablename__ = "configuracao_custo"
    __table_args__ = (
        CheckConstraint("id_configuracao = 1", name="ck_configuracao_custo_linha_unica"),
        CheckConstraint(
            "primeira_hora_tecnico >= 0 AND hora_tecnico >= 0 AND tempo_deslocamento_tecnico >= 0 "
            "AND quilometragem >= 0",
            name="ck_configuracao_custo_valores_nao_negativos"),
    )

    id_configuracao = Column(SmallInteger, primary_key=True, autoincrement=False, default=1)
    primeira_hora_tecnico = Column(Numeric(10, 2), nullable=False, server_default=text("0"))
    hora_tecnico = Column(Numeric(10, 2), nullable=False, server_default=text("0"))
    tempo_deslocamento_tecnico = Column(Numeric(10, 2), nullable=False, server_default=text("0"))
    quilometragem = Column(Numeric(10, 2), nullable=False, server_default=text("0"))
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
