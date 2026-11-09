import uuid

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, JSON, CheckConstraint, Index, Uuid, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.database import Base

JSONB_COMPAT = JSON().with_variant(JSONB(), "postgresql")


class SyncEvento(Base):
    """
    Idempotencia e rastreio da sincronizacao offline (SDD 4.7, 6.12).
    client_event_id e a chave de idempotencia: reenvio devolve o resultado anterior, sem novo efeito.
    Transacao por evento. Eventos da mesma visita sao ordenaveis por ocorrido_em.
    Nao armazenar tokens/senhas/CPF completo em payload alem do estritamente necessario.
    """
    __tablename__ = "sync_evento"
    __table_args__ = (
        CheckConstraint("resultado IN ('aplicado', 'duplicado', 'rejeitado')", name="ck_sync_evento_resultado"),
        Index("ix_sync_evento_id_os", "id_os"),
        Index("ix_sync_evento_id_visita_ocorrido_em", "id_visita", "ocorrido_em"),
        Index("ix_sync_evento_id_tecnico_recebido_em", "id_tecnico", "recebido_em"),
    )

    # Uuid genérico do SQLAlchemy 2.0: UUID nativo no PostgreSQL (igual à coluna existente) e CHAR(32) no SQLite.
    client_event_id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_tecnico = Column(Integer, ForeignKey("tecnico.id_tecnico"), nullable=False)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"))
    id_visita = Column(Integer, ForeignKey("visita.id_visita"))
    tipo = Column(String(50), nullable=False)
    ocorrido_em = Column(DateTime(timezone=True), nullable=False)   # relogio do aparelho
    recebido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())  # relogio do servidor
    payload = Column(JSONB_COMPAT, nullable=False, server_default=text("'{}'"))
    resultado = Column(String(12), nullable=False)   # aplicado | duplicado | rejeitado
    codigo = Column(String(40))                      # ex.: CONFLITO_ADMINISTRATIVO
    detalhe = Column(Text)
