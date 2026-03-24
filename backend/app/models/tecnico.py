from sqlalchemy import Column, Integer, String, Boolean, Enum
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.schemas.base_schemas import UserRole


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
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in obj]), nullable=False,
                  default=UserRole.TECNICO.value)
    is_active = Column(Boolean, nullable=False, default=True)
    banco = Column(String(100))
    agencia = Column(String(50))
    conta = Column(String(50))
    pix = Column(String(100))

    chamados = relationship("OrdemServico", back_populates="tecnico")

    @property
    def dados_bancarios(self):
        if not any([self.banco, self.agencia, self.conta, self.pix]):
            return None
        return {"banco": self.banco, "agencia": self.agencia, "conta": self.conta, "pix": self.pix}