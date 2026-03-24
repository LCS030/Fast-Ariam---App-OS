from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base


class ServicoFoto(Base):
    __tablename__ = "servico_foto"
    id_foto = Column(Integer, primary_key=True, autoincrement=True)
    id_servico = Column(Integer, ForeignKey("servico_equipamento.id_servico", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(20), nullable=False)  # 'defeito' ou 'conserto'
    url = Column(String(255), nullable=False)

    servico = relationship("ServicoEquipamento", back_populates="fotos")