from sqlalchemy import Column, Integer, String, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base


class Comprovante(Base):
    __tablename__ = "comprovante"
    __table_args__ = (
        CheckConstraint("tipo IN ('pedagio', 'frete')", name="ck_comprovante_tipo"),
    )

    id_comprovante = Column(Integer, primary_key=True, autoincrement=True)
    id_visita = Column(Integer, ForeignKey("visita.id_visita", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(50), nullable=False)  # 'pedagio' ou 'frete'
    url = Column(String(255), nullable=False)
    sha256 = Column(String(64))  # SHA-256 dos bytes recebidos (calculado pelo servidor)

    visita = relationship("Visita", back_populates="comprovantes")
