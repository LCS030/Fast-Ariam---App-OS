from sqlalchemy import Column, Integer, String, ForeignKey, Numeric
from sqlalchemy.orm import relationship
from app.db.database import Base


class Material(Base):
    __tablename__ = "material"
    id_material = Column(Integer, primary_key=True, autoincrement=True)
    id_servico = Column(Integer, ForeignKey("servico_equipamento.id_servico"), nullable=False)
    nome = Column(String(100), nullable=False)
    quantidade = Column(Integer, nullable=False)
    valor = Column(Numeric(10, 2), nullable=False)
    servico = relationship("ServicoEquipamento", back_populates="materiais_utilizados")