from sqlalchemy import Column, Integer, String, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.db.database import Base


class ServicoEquipamento(Base):
    __tablename__ = "servico_equipamento"
    id_servico = Column(Integer, primary_key=True, autoincrement=True)
    id_visita = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    numero_serie_atendido = Column(String(100), nullable=False)
    nome_equipamento = Column(String(100), nullable=True)
    defeitos_principais = Column(JSON, nullable=False, server_default='[]')
    defeito_outros_descricao = Column(Text)
    sub_defeitos_refrigeracao = Column(JSON, nullable=False, server_default='[]')
    sub_defeitos_compressor = Column(JSON, nullable=False, server_default='[]')
    sub_defeitos_vazamento = Column(JSON, nullable=False, server_default='[]')
    vazamento_ponto_descricao = Column(Text)
    sub_defeitos_outros = Column(JSON, nullable=False, server_default='[]')
    sub_defeitos_iluminacao = Column(JSON, nullable=False, server_default='[]')
    sub_defeitos_estrutura = Column(JSON, nullable=False, server_default='[]')
    visita = relationship("Visita", back_populates="servicos_realizados")
    materiais_utilizados = relationship("Material", back_populates="servico", cascade="all, delete-orphan")
