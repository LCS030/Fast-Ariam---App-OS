from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Text, ForeignKey, Numeric, DateTime, JSON, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.crypto import TextoCifrado
from app.db.database import Base


class Visita(Base):
    __tablename__ = "visita"
    id_visita = Column(Integer, primary_key=True, autoincrement=True)
    id_os = Column(Integer, ForeignKey("ordem_servico.id_os"), nullable=False)
    data_visita = Column(Date, nullable=False)

    # --- LEGADO: horarios HH:mm (VARCHAR(5)). Derivados dos *_em abaixo ate os fronts migrarem. Nao ampliar uso. ---
    hora_inicio_deslocamento = Column(String(5))
    hora_chegada_cliente = Column(String(5))
    hora_inicio_atendimento = Column(String(5))
    hora_fim_atendimento = Column(String(5))
    # SDD 4.4: NOT NULL DEFAULT 0. Calculado: (km_fim_ida - km_inicio_ida) + (km_fim_volta - km_inicio_volta).
    km_total = Column(Integer, nullable=False, default=0, server_default=text("0"))
    # Campos para rastreamento de deslocamento IDA
    km_inicio_ida = Column(Integer)
    hora_inicio_ida = Column(String(5))   # legado
    km_fim_ida = Column(Integer)
    hora_fim_ida = Column(String(5))      # legado
    # Campos para rastreamento de deslocamento VOLTA
    km_inicio_volta = Column(Integer)
    hora_inicio_volta = Column(String(5))  # legado
    km_fim_volta = Column(Integer)
    hora_fim_volta = Column(String(5))     # legado

    # --- Novos (SDD 4.7): momento real da acao, vindo do aparelho, com fuso (TIMESTAMPTZ) ---
    ida_inicio_em = Column(DateTime(timezone=True))
    ida_fim_em = Column(DateTime(timezone=True))
    atendimento_inicio_em = Column(DateTime(timezone=True))
    atendimento_fim_em = Column(DateTime(timezone=True))
    volta_inicio_em = Column(DateTime(timezone=True))
    volta_fim_em = Column(DateTime(timezone=True))

    valor_pedagio = Column(Numeric(10, 2), nullable=False, default=0.00, server_default=text("0"))
    valor_frete_devolucao = Column(Numeric(10, 2), nullable=False, default=0.00, server_default=text("0"))
    descricao_servico_executado = Column(Text)
    # LEGADO: ajudantes estao fora do escopo v0.3. Colunas mantidas so para historico; sem uso/tela/calculo.
    nome_ajudante = Column(String(100))
    telefone_ajudante = Column(String(20))
    servico_finalizado = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    pendencia = Column(Text)
    odometro_inicio_url = Column(String(255))
    odometro_fim_url = Column(String(255))
    # URLs das fotos de deslocamento (ida e volta, inicio e fim) - referencia/path do objeto no Storage
    foto_inicio_ida_url = Column(String(255))
    foto_fim_ida_url = Column(String(255))
    foto_inicio_volta_url = Column(String(255))
    foto_fim_volta_url = Column(String(255))

    # --- Assinatura do cliente na visita (SDD 4.7, PR-10, PR-35) ---
    assinatura_url = Column(String(255))            # caminho no Storage
    # quem assinou: CIFRADO em repouso (TEXT apos a 0014); limite de 100 caracteres validado no servico/esquema. O selo
    # de integridade e calculado sobre o valor em CLARO (lido pelo ORM), entao nao muda ao cifrar.
    nome_cliente_assinatura = Column(TextoCifrado("visita.nome_cliente_assinatura"))
    # CPF (11 digitos, validado pelo backend em `cpf_valido`), CIFRADO em repouso. O CHECK de 11 digitos foi retirado
    # (nao se aplica a texto cifrado); a regra continua garantida na camada de servico/esquema.
    documento_cliente = Column(TextoCifrado("visita.documento_cliente"))

    # --- Integridade (SHA-256 dos arquivos e selo HMAC da visita) ---
    assinatura_sha256 = Column(String(64))          # hash dos bytes da assinatura ANTES de cifrar
    # {campo_url: sha256} das fotos de odometro/deslocamento (6 colunas *_url desta tabela)
    arquivos_sha256 = Column(JSON().with_variant(JSONB(), "postgresql"))
    selo_integridade = Column(String(64))           # HMAC-SHA256(INTEGRITY_KEY, JSON canonico) ao finalizar atendimento
    selo_versao = Column(Integer)                   # versao do esquema canonico do selo

    comprovantes = relationship("Comprovante", back_populates="visita", cascade="all, delete-orphan")
    ordem_servico = relationship("OrdemServico", back_populates="visitas")
    servicos_realizados = relationship("ServicoEquipamento", back_populates="visita", cascade="all, delete-orphan")

    @property
    def comprovante_pedagio_urls(self):
        return [c.url for c in self.comprovantes if c.tipo == 'pedagio']

    @property
    def comprovante_frete_urls(self):
        return [c.url for c in self.comprovantes if c.tipo == 'frete']
