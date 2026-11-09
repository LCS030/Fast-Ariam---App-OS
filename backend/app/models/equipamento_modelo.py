from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, Integer, String, func, text

from app.db.database import Base


class EquipamentoModelo(Base):
    """
    Catálogo de modelos de equipamento (SDD 4.8, PRD RF-23 / RN-40). Só o NOME do modelo
    (ex.: "Freezer vertical modelo X"). Nunca é excluído: desativação lógica (`is_active`), que só impede NOVOS vínculos.
    Nomes únicos sem diferenciar maiúsculas (índice em lower(modelo)).
    Nomes de constraints/índices idênticos aos de backend/migrations/0007_equipamento_os.sql.
    """
    __tablename__ = "equipamento_modelo"
    __table_args__ = (
        CheckConstraint("modelo = btrim(modelo) AND length(modelo) > 0", name="ck_equipamento_modelo_modelo"),
    )

    id_equipamento_modelo = Column(Integer, primary_key=True, autoincrement=True)
    modelo = Column(String(100), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# Índice único funcional (nomes únicos sem diferenciar maiúsculas); definido após a classe para referenciar a coluna.
Index("ux_equipamento_modelo_modelo_lower", func.lower(EquipamentoModelo.modelo), unique=True)
