import uuid

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.sql import func

from app.db.database import Base

TIPOS_ARQUIVO = ("foto_defeito", "foto_conserto", "foto_deslocamento", "comprovante_pedagio", "comprovante_frete",
                 "assinatura")


class SyncArquivo(Base):
    """
    Arquivo recebido pela sincronização offline (SDD 6.12). `client_file_id` (gerado no aparelho) é a chave de
    idempotência: reenviar devolve a `url` já gravada. A ligação ao registro final (foto de serviço, odômetro,
    comprovante, assinatura) só ocorre quando o evento que o referencia (`foto_ref` / `assinatura_ref`) é aplicado.
    Migração: backend/migrations/0009_sync_arquivo.sql.
    """
    __tablename__ = "sync_arquivo"
    __table_args__ = (
        CheckConstraint("tipo_arquivo IN ('foto_defeito', 'foto_conserto', 'foto_deslocamento', "
                        "'comprovante_pedagio', 'comprovante_frete', 'assinatura')", name="ck_sync_arquivo_tipo"),
        Index("ix_sync_arquivo_id_tecnico", "id_tecnico"),
        Index("ix_sync_arquivo_id_visita", "id_visita"),
    )

    client_file_id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    id_tecnico = Column(Integer, ForeignKey("tecnico.id_tecnico"), nullable=False)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"), nullable=False)
    id_visita = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    tipo_arquivo = Column(String(30), nullable=False)
    url = Column(String(255), nullable=False)
    recebido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
