from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.database import Base


class Pausa(Base):
    __tablename__ = "pausa"
    id_pausa = Column(Integer, primary_key=True, autoincrement=True)
    visita_id = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    motivo = Column(String(100), nullable=False)
    descricao = Column(Text)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    por_tecnico_id = Column(Integer, ForeignKey("tecnico.id_tecnico"))
    is_ativa = Column(Boolean, nullable=False, default=True)

    visita = relationship("Visita", backref="pausas")
    tecnico = relationship("Tecnico")

    def __repr__(self):
        return f"<Pausa id={self.id_pausa} visita={self.visita_id} motivo={self.motivo} ativa={self.is_ativa}>"
