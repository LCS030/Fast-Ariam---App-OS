from sqlalchemy import (Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import relationship
from app.db.database import Base


class ServicoEquipamento(Base):
    """
    Registro de serviço de UM equipamento da OS em UMA visita (SDD 4.5).

    v0.5: o equipamento vem da OS (`id_os_equipamento`) e o registro é criado pelo SERVIDOR quando a visita abre; o
    técnico só o preenche (defeitos, materiais, fotos e "Salvar conserto"). `numero_serie_atendido` e
    `nome_equipamento` são LEGADO somente leitura (`is_legado = true`). Nomes de constraints idênticos aos de
    backend/migrations/0007_equipamento_os.sql.
    """
    __tablename__ = "servico_equipamento"
    __table_args__ = (
        CheckConstraint("is_legado OR id_os_equipamento IS NOT NULL", name="ck_servico_equip_vinculo"),
        CheckConstraint("id_os_equipamento IS NOT NULL OR numero_serie_atendido IS NOT NULL",
                        name="ck_servico_equip_identificacao"),
        UniqueConstraint("id_visita", "id_os_equipamento", name="uq_servico_equip_visita_os_equipamento"),
        Index("ix_servico_equipamento_id_os_equipamento", "id_os_equipamento"),
    )

    id_servico = Column(Integer, primary_key=True, autoincrement=True)
    id_visita = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    id_os_equipamento = Column(Integer, ForeignKey("os_equipamento.id_os_equipamento", ondelete="RESTRICT"),
                               nullable=True)
    # Marca de "conserto salvo" (PRD RN-47): preenchida só por POST .../salvar-conserto.
    conserto_salvo_em = Column(DateTime(timezone=True), nullable=True)
    # O default de coluna é False (registros criados pelo servidor). O server_default true existe só na fase de
    # expansão da migração 0007, para o backend antigo continuar inserindo sem vínculo.
    is_legado = Column(Boolean, nullable=False, default=False, server_default=text("true"))
    # LEGADO (somente leitura): texto livre digitado pelo técnico antes da v0.5.
    numero_serie_atendido = Column(String(100), nullable=True)
    nome_equipamento = Column(String(100), nullable=True)
    defeito_outros_descricao = Column(Text)
    vazamento_ponto_descricao = Column(Text)

    visita = relationship("Visita", back_populates="servicos_realizados")
    equipamento = relationship("OsEquipamento")
    materiais_utilizados = relationship("Material", back_populates="servico", cascade="all, delete-orphan")
    defeitos = relationship("ServicoDefeito", back_populates="servico", cascade="all, delete-orphan")
    fotos = relationship("ServicoFoto", back_populates="servico", cascade="all, delete-orphan")

    @property
    def modelo(self):
        """Modelo do equipamento da OS (somente leitura); serviços legados usam o nome digitado na época."""
        if self.equipamento is not None:
            return self.equipamento.modelo
        return self.nome_equipamento

    @property
    def numero_serie(self):
        """Série do equipamento da OS (somente leitura); serviços legados usam a série digitada na época."""
        if self.equipamento is not None:
            return self.equipamento.numero_serie
        return self.numero_serie_atendido

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
