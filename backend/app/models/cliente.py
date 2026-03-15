from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.db.database import Base


class Cliente(Base):
    __tablename__ = "cliente"
    id_cliente = Column(Integer, primary_key=True, autoincrement=True)
    razao_social = Column(String(100), nullable=False)
    codigo = Column(Integer, unique=True, nullable=False)
    contato_principal_nome = Column(String(100))
    contato_principal_telefone = Column(String(20))
    telefone = Column(String(20))
    endereco = Column(String(200))
    numero = Column(String(20))
    bairro = Column(String(100))
    cidade = Column(String(100))
    uf = Column(String(2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    chamados = relationship("OrdemServico", back_populates="cliente")