from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base

class ServicoEquipamento(Base):
    __tablename__ = "servico_equipamento"
    id_servico = Column(Integer, primary_key=True, autoincrement=True)
    id_visita = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    numero_serie_atendido = Column(String(100), nullable=False)
    nome_equipamento = Column(String(100), nullable=True)
    defeito_outros_descricao = Column(Text)
    vazamento_ponto_descricao = Column(Text)

    visita = relationship("Visita", back_populates="servicos_realizados")
    materiais_utilizados = relationship("Material", back_populates="servico", cascade="all, delete-orphan")
    defeitos = relationship("ServicoDefeito", back_populates="servico", cascade="all, delete-orphan")
    fotos = relationship("ServicoFoto", back_populates="servico", cascade="all, delete-orphan")

    @property
    def defeitos_principais(self): return[d.defeito for d in self.defeitos if d.tipo == 'principal']
    @property
    def sub_defeitos_refrigeracao(self): return[d.defeito for d in self.defeitos if d.tipo == 'refrigeracao']
    @property
    def sub_defeitos_compressor(self): return[d.defeito for d in self.defeitos if d.tipo == 'compressor']
    @property
    def sub_defeitos_vazamento(self): return[d.defeito for d in self.defeitos if d.tipo == 'vazamento']
    @property
    def sub_defeitos_outros(self): return[d.defeito for d in self.defeitos if d.tipo == 'outros']
    @property
    def sub_defeitos_iluminacao(self): return[d.defeito for d in self.defeitos if d.tipo == 'iluminacao']
    @property
    def sub_defeitos_estrutura(self): return[d.defeito for d in self.defeitos if d.tipo == 'estrutura']
    @property
    def fotos_defeito(self): return [f.url for f in self.fotos if f.tipo == 'defeito']
    @property
    def fotos_conserto(self): return[f.url for f in self.fotos if f.tipo == 'conserto']