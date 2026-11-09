"""
Cria o primeiro administrador (bootstrap). Não insere OS, clientes nem dados de exemplo.

Variáveis (opcionais):
  SEED_ADMIN_EMAIL     e-mail do administrador (padrão: admin@fastariam.com)
  SEED_ADMIN_PASSWORD  senha inicial (8 a 72 bytes). Se ausente, uma senha aleatória é gerada e exibida UMA vez.

Nenhuma senha fixa existe no código. Troque a senha após o primeiro login (PATCH /api/tecnicos/me/password).
Os documentos do admin (CPF/CNPJ, NOT NULL no banco) são marcadores; o administrador pode corrigi-los via
PATCH /api/tecnicos/{id}.
"""
import importlib
import os
import pkgutil
import secrets
import sys

import app.models as _pacote_models
from sqlalchemy import inspect
from app.core.config import AUTO_CREATE_TABLES
from app.core.security import hash_password
from app.db.database import SessionLocal, engine, Base
from app.schemas.token import validar_forca_senha


def importar_modelos() -> None:
    """Importa todos os módulos de app.models para registrar as tabelas no metadata (inclusive novos modelos)."""
    for modulo in pkgutil.iter_modules(_pacote_models.__path__):
        importlib.import_module(f"{_pacote_models.__name__}.{modulo.name}")


def semear_banco():
    importar_modelos()
    from app.models.tecnico import Tecnico  # noqa: E402  (depois de importar_modelos)

    if AUTO_CREATE_TABLES:
        print("Criando tabelas ausentes (AUTO_CREATE_TABLES=true)...")
        Base.metadata.create_all(bind=engine)
    elif not inspect(engine).has_table(Tecnico.__tablename__):
        print("ERRO: as tabelas não existem. Aplique as migrações do banco (ou, só em dev, use AUTO_CREATE_TABLES=true).")
        sys.exit(1)

    email_admin = os.getenv("SEED_ADMIN_EMAIL", "admin@fastariam.com").strip().lower()
    senha_env = os.getenv("SEED_ADMIN_PASSWORD")
    senha_gerada = senha_env is None or senha_env == ""
    senha = secrets.token_urlsafe(12) if senha_gerada else validar_forca_senha(senha_env)

    db = SessionLocal()
    try:
        admin_existente = db.query(Tecnico).filter(Tecnico.email == email_admin).first()

        if not admin_existente:
            print("Criando o primeiro Administrador...")
            novo_admin = Tecnico(
                nome="Administrador Mestre",
                cpf="000.000.000-00",  # marcador (NOT NULL): corrigir via PATCH /api/tecnicos/{id}
                cnpj="00.000.000/0000-00",  # marcador (NOT NULL, UNIQUE): idem
                email=email_admin,
                password_hash=hash_password(senha),
                role="admin",
                is_active=True
            )
            db.add(novo_admin)
            db.commit()
            print(f"Administrador criado. E-mail: {email_admin}")
            if senha_gerada:
                print(f"Senha inicial (gerada, exibida apenas agora): {senha}")
            print("Troque a senha após o primeiro login.")
        else:
            print("O banco já possui o Administrador (nada foi alterado).")
    finally:
        db.close()


if __name__ == "__main__":
    semear_banco()
