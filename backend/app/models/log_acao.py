from sqlalchemy import BigInteger, Column, Integer, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.database import Base

JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


class LogAcao(Base):
    """
    Trilha de auditoria (SDD 4.7, PR-20). Registra usuario, papel, OS relacionada, acao, instante e payload minimo.
    Nao registrar tokens, senhas, CPF completo, dados bancarios nem binarios. Sem rotina de purga nesta versao.
    id_usuario e NULL para acoes do sistema (ex.: CONFLITO_ADMINISTRATIVO, SY-05); nesse caso papel = 'sistema'.
    """
    __tablename__ = "log_acao"
    __table_args__ = (
        Index("ix_log_acao_id_os_criado_em", "id_os", "criado_em"),
        Index("ix_log_acao_id_usuario", "id_usuario"),
    )

    # BIGINT no PostgreSQL; INTEGER no SQLite (autoincrement so funciona com INTEGER PRIMARY KEY).
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"))
    id_usuario = Column(Integer, ForeignKey("tecnico.id_tecnico"))
    papel = Column(String(10))        # 'admin' | 'tecnico' | 'sistema'
    acao = Column(String(50), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    payload = Column(JSONB_COMPAT)
