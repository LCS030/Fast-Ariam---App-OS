# import enum
from sqlalchemy import Column, Integer, String, Boolean, JSON, Enum
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.schemas.base_schemas import UserRole


# class UserRole(enum.Enum):
#     admin = "admin"
#     tecnico = "tecnico"


class Tecnico(Base):
    __tablename__ = "tecnico"
    id_tecnico = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    cnpj = Column(String(18), nullable=False, unique=True)
    cpf = Column(String(14), nullable=False)
    inscricao_estadual = Column(String(50))
    email = Column(String(100), nullable=False, unique=True)
    telefone = Column(String(20))
    password_hash = Column(String(100), nullable=False)
    # role = Column(Enum(UserRole), nullable=False, default=UserRole.tecnico)
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in obj]), nullable=False,
                  default=UserRole.TECNICO.value)
    is_active = Column(Boolean, nullable=False, default=True)
    dados_bancarios = Column(JSON)
    chamados = relationship("OrdemServico", back_populates="tecnico")
