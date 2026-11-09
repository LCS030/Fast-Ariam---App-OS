from sqlalchemy import Column, Integer, String, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.db.database import Base


class ServicoFoto(Base):
    __tablename__ = "servico_foto"
    __table_args__ = (
        CheckConstraint("tipo IN ('defeito', 'conserto')", name="ck_servico_foto_tipo"),
    )

    id_foto = Column(Integer, primary_key=True, autoincrement=True)
    id_servico = Column(Integer, ForeignKey("servico_equipamento.id_servico", ondelete="CASCADE"), nullable=False)
    tipo = Column(String(20), nullable=False)  # 'defeito' ou 'conserto'
    url = Column(String(255), nullable=False)

    servico = relationship("ServicoEquipamento", back_populates="fotos")
