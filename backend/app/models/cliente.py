from sqlalchemy import Column, Integer, String, Boolean
from sqlalchemy.orm import relationship
from app.core.crypto import TextoCifrado
from app.db.database import Base


class Cliente(Base):
    __tablename__ = "cliente"
    id_cliente = Column(Integer, primary_key=True, autoincrement=True)
    razao_social = Column(String(100), nullable=False)
    codigo = Column(Integer, unique=True, nullable=False)
    # Contato principal = dado de pessoa fisica: CIFRADO em repouso (coluna TEXT apos a migracao 0014). Os limites de
    # 100/20 caracteres continuam validados nos schemas (app/schemas/cliente.py) ANTES de cifrar. `telefone` (comercial,
    # PJ) permanece em claro.
    contato_principal_nome = Column(TextoCifrado("cliente.contato_principal_nome"))
    contato_principal_telefone = Column(TextoCifrado("cliente.contato_principal_telefone"))
    telefone = Column(String(20))
    endereco = Column(String(200))
    numero = Column(String(20))
    bairro = Column(String(100))
    cidade = Column(String(100))
    uf = Column(String(2), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    chamados = relationship("OrdemServico", back_populates="cliente")