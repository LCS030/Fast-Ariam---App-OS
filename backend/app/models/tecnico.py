import re

from sqlalchemy import Column, Integer, String, Boolean, Enum
from sqlalchemy.orm import relationship, validates
from app.core.crypto import TextoCifrado, indice_cego
from app.db.database import Base
from app.schemas.base_schemas import UserRole


class Tecnico(Base):
    __tablename__ = "tecnico"
    id_tecnico = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String(100), nullable=False)
    # Campos sensíveis cifrados com AES-256-GCM (app.core.crypto). Exceção deliberada: e-mail fica em claro (chave de login).
    cnpj = Column(TextoCifrado("tecnico.cnpj"), nullable=False)
    # Índice cego do CNPJ (HMAC-SHA256 dos 14 dígitos): único e pesquisável sem guardar o CNPJ em claro. Mantido
    # automaticamente por _atualizar_indice_cnpj; é ele (e não o cnpj cifrado) que garante a unicidade (RN-06).
    cnpj_idx = Column(String(64), nullable=False, unique=True)
    cpf = Column(TextoCifrado("tecnico.cpf"), nullable=False)
    inscricao_estadual = Column(String(50))
    email = Column(String(100), nullable=False, unique=True)
    telefone = Column(TextoCifrado("tecnico.telefone"))
    password_hash = Column(String(100), nullable=False)
    role = Column(Enum(UserRole, values_callable=lambda obj: [e.value for e in obj]), nullable=False,
                  default=UserRole.TECNICO.value)
    is_active = Column(Boolean, nullable=False, default=True)
    banco = Column(TextoCifrado("tecnico.banco"))
    agencia = Column(TextoCifrado("tecnico.agencia"))
    conta = Column(TextoCifrado("tecnico.conta"))
    pix = Column(TextoCifrado("tecnico.pix"))

    # ordem_servico tem duas FKs para tecnico (id_tecnico_atribuido e cancelado_por): desambiguar.
    chamados = relationship("OrdemServico", back_populates="tecnico",
                            foreign_keys="OrdemServico.id_tecnico_atribuido")

    @staticmethod
    def indice_do_cnpj(cnpj: str) -> str:
        """Índice cego do CNPJ: só os dígitos, para a busca ignorar a máscara (00.000.000/0000-00 == 00000000000000)."""
        return indice_cego(re.sub(r"\D", "", cnpj or ""), "tecnico.cnpj")

    @validates("cnpj")
    def _atualizar_indice_cnpj(self, _chave, valor):
        self.cnpj_idx = self.indice_do_cnpj(valor) if valor is not None else None
        return valor

    @property
    def dados_bancarios(self):
        if not any([self.banco, self.agencia, self.conta, self.pix]):
            return None
        return {"banco": self.banco, "agencia": self.agencia, "conta": self.conta, "pix": self.pix}