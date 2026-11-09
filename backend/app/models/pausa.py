from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, CheckConstraint, text
from sqlalchemy.orm import relationship, synonym
from sqlalchemy.sql import func
from app.db.database import Base


class Pausa(Base):
    __tablename__ = "pausa"
    # Nomes identicos aos de backend/migrations/0001_alinhar_sdd_v03.sql
    __table_args__ = (
        CheckConstraint("por_papel IS NULL OR por_papel IN ('admin', 'tecnico')", name="ck_pausa_por_papel"),
        CheckConstraint(
            "motivo IN ('Peça pendente', 'Cliente ausente', 'Condições inseguras', 'Aguardando aprovação', 'Outro')",
            name="ck_pausa_motivo"),
        CheckConstraint("motivo <> 'Outro' OR length(btrim(coalesce(descricao, ''))) > 0",
                        name="ck_pausa_outro_descricao"),
        CheckConstraint("NOT is_ativa OR encerrada_em IS NULL", name="ck_pausa_ativa_sem_encerramento"),
    )

    id_pausa = Column(Integer, primary_key=True, autoincrement=True)
    visita_id = Column(Integer, ForeignKey("visita.id_visita"), nullable=False)
    motivo = Column(String(100), nullable=False)
    descricao = Column(Text)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    # SDD 4.7: autor da pausa (tecnico OU admin). Substitui por_tecnico_id.
    # Pausas legadas feitas por admin tem NULL (o codigo antigo gravava NULL para admin) - ver migrations/README.md.
    por_usuario_id = Column(Integer, ForeignKey("tecnico.id_tecnico"))
    por_papel = Column(String(10))                 # 'admin' | 'tecnico'
    is_ativa = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    encerrada_em = Column(DateTime(timezone=True))  # preenchido quando is_ativa vira false

    # A coluna legada pausa.por_tecnico_id continua no banco ate a contracao (0004) mas NAO e mapeada.
    # Alias de compatibilidade para o codigo atual (Pausa(por_tecnico_id=...)); remover quando o Backend migrar.
    por_tecnico_id = synonym("por_usuario_id")

    visita = relationship("Visita", backref="pausas")
    usuario = relationship("Tecnico", foreign_keys=[por_usuario_id])
    tecnico = synonym("usuario")  # alias de compatibilidade

    def __repr__(self):
        return f"<Pausa id={self.id_pausa} visita={self.visita_id} motivo={self.motivo} ativa={self.is_ativa}>"
