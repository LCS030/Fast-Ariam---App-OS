from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Text, ForeignKey, Enum, DateTime, CheckConstraint, text,
)
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.schemas.base_schemas import StatusChamado


class OrdemServico(Base):
    __tablename__ = "ordem_servico"
    # Nomes dos CHECKs identicos aos de backend/migrations/0002_constraints_estado.sql
    __table_args__ = (
        # SDD 4.7 / PRD v0.3: Pendente => sem tecnico atribuido.
        CheckConstraint("status <> 'Pendente' OR id_tecnico_atribuido IS NULL",
                        name="ck_os_pendente_sem_tecnico"),
        # SDD 4.3: 'Aberto' e legado; nenhuma operacao nova pode grava-lo.
        CheckConstraint("status <> 'Aberto'", name="ck_os_status_sem_aberto"),
        # SDD 4.7: motivo obrigatorio quando cancelada.
        CheckConstraint("NOT is_cancelled OR length(btrim(coalesce(motivo_cancelamento, ''))) > 0",
                        name="ck_os_cancelamento_motivo"),
    )

    id_os = Column(Integer, primary_key=True, autoincrement=True)
    id_cliente = Column(Integer, ForeignKey("cliente.id_cliente"), nullable=False)
    id_tecnico_atribuido = Column(Integer, ForeignKey("tecnico.id_tecnico"), nullable=True)
    # SDD 4.3: NOT NULL, DEFAULT 'Pendente'. O servico de criacao define 'Agendado' quando ha tecnico ativo.
    status = Column(Enum(StatusChamado, values_callable=lambda obj: [e.value for e in obj]), nullable=False,
                    default=StatusChamado.PENDENTE.value, server_default=text("'Pendente'"))
    is_cancelled = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    data_abertura = Column(Date, nullable=False)
    data_agendamento = Column(Date)
    data_conclusao = Column(Date)
    descricao_cliente = Column(Text)
    pedido = Column(String(100))
    data_faturamento = Column(Date)
    em_garantia = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    # DESCONTINUADA (SDD 4.7 / PR-35): a assinatura agora e da visita (visita.assinatura_url).
    # Mantida somente para dados antigos; nao gravar em novas operacoes.
    assinatura_cliente_url = Column(String(255))

    # Cancelamento (SDD 4.7). Cancelado NAO e valor de enum: is_cancelled + motivo/data/autor.
    motivo_cancelamento = Column(Text)
    cancelado_em = Column(DateTime(timezone=True))
    cancelado_por = Column(Integer, ForeignKey("tecnico.id_tecnico"))  # id do administrador

    # Ha duas FKs para tecnico (atribuido e cancelado_por): foreign_keys explicito evita ambiguidade.
    cliente = relationship("Cliente", back_populates="chamados")
    tecnico = relationship("Tecnico", back_populates="chamados", foreign_keys=[id_tecnico_atribuido])
    cancelado_por_usuario = relationship("Tecnico", foreign_keys=[cancelado_por])
    visitas = relationship("Visita", back_populates="ordem_servico", cascade="all, delete-orphan")
    # v0.5: equipamentos a consertar (modelo + série) vinculados pelo admin. RESTRICT: não há cascata de exclusão.
    equipamentos = relationship("OsEquipamento", back_populates="ordem_servico",
                                order_by="OsEquipamento.id_os_equipamento")
    # custo_os (1:1) e declarado em app/models/custo_os.py com backref "custo".

    # Nota: a coluna legada ordem_servico.is_completed (BOOLEAN NOT NULL DEFAULT false) existe no banco
    # remoto, mas NAO e mapeada aqui (nenhum codigo a usa). Ver migrations/0004_contracao_opcional.sql.
