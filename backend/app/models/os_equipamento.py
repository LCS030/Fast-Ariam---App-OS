from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import relationship

from app.db.database import Base


class OsEquipamento(Base):
    """
    Equipamento a consertar vinculado a uma OS pelo administrador (modelo do catálogo + número de série).
    SDD 4.8, PRD RF-24 / RN-41 / RN-42. Pertence à OS (não à visita nem ao técnico): é compartilhado entre as visitas
    e o técnico só o LÊ. Série única por OS sem diferenciar maiúsculas. FKs RESTRICT: nada é apagado em cascata.
    """
    __tablename__ = "os_equipamento"
    __table_args__ = (
        CheckConstraint("numero_serie = btrim(numero_serie) AND length(numero_serie) > 0",
                        name="ck_os_equipamento_numero_serie"),
        CheckConstraint("origem IN ('admin', 'backfill_legado')", name="ck_os_equipamento_origem"),
        Index("ix_os_equipamento_id_equipamento_modelo", "id_equipamento_modelo"),
    )

    id_os_equipamento = Column(Integer, primary_key=True, autoincrement=True)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os", ondelete="RESTRICT"), nullable=False)
    id_equipamento_modelo = Column(Integer, ForeignKey("equipamento_modelo.id_equipamento_modelo", ondelete="RESTRICT"),
                                   nullable=False)
    numero_serie = Column(String(100), nullable=False)
    origem = Column(String(20), nullable=False, default="admin", server_default=text("'admin'"))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    ordem_servico = relationship("OrdemServico", back_populates="equipamentos")
    equipamento_modelo = relationship("EquipamentoModelo")

    @property
    def modelo(self) -> str:
        """Nome do modelo do catálogo (campo `modelo` das respostas)."""
        return self.equipamento_modelo.modelo if self.equipamento_modelo is not None else ""


# Série única por OS, sem diferenciar maiúsculas (índice funcional).
Index("ux_os_equipamento_os_serie_upper", OsEquipamento.id_os, func.upper(OsEquipamento.numero_serie), unique=True)
