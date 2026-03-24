from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base


class ServicoDefeito(Base):
    __tablename__ = "servico_defeito"
    id_defeito = Column(Integer, primary_key=True, autoincrement=True)
    id_servico = Column(Integer, ForeignKey("servico_equipamento.id_servico", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(50), nullable=False)
    defeito = Column(String(100), nullable=False)

    servico = relationship("ServicoEquipamento", back_populates="defeitos")