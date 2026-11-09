"""
Configuração global dos testes.

REGRA CRÍTICA: os testes NUNCA usam o DATABASE_URL real (Supabase de produção). Este arquivo define um SQLite
temporário e uma SECRET_KEY de teste ANTES de qualquer import de `app.*`, sobrescrevendo o que vier do ambiente/.env
(python-dotenv não sobrescreve variáveis já definidas).
"""
import os
import shutil
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# --- Ambiente isolado (antes de importar a aplicação) ---------------------------------------------------------------
_TMP_DIR = tempfile.mkdtemp(prefix="fast_ariam_tests_")
_SQLITE_PATH = os.path.join(_TMP_DIR, "test.db").replace("\\", "/")

os.environ["DATABASE_URL"] = f"sqlite:///{_SQLITE_PATH}"
os.environ["SECRET_KEY"] = "chave-de-teste-nao-usar-em-producao-0123456789abcdef"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "30"
os.environ["ENV"] = "test"
os.environ["CORS_ORIGINS"] = "http://localhost:5173,http://localhost:3000"
os.environ["AUTO_CREATE_TABLES"] = "false"  # as tabelas são criadas abaixo, no SQLite temporário

from app.db.database import engine, Base, get_db  # noqa: E402
from app.main import app  # noqa: E402  (importa todos os modelos)

# Trava dupla: aborta a sessão inteira se, por qualquer motivo, o engine não for o SQLite temporário.
if engine.url.get_backend_name() != "sqlite" or _TMP_DIR.replace("\\", "/") not in str(engine.url).replace("\\", "/"):
    pytest.exit("ABORTADO: os testes só podem rodar contra o SQLite temporário.", returncode=2)


def _remover_constraints_exclusivas_do_postgres() -> None:
    """CHECKs com funções/operadores só do PostgreSQL (btrim, ~) não existem no SQLite; o PostgreSQL continua os aplicando."""
    from sqlalchemy import CheckConstraint
    for tabela in Base.metadata.sorted_tables:
        for constraint in list(tabela.constraints):
            if isinstance(constraint, CheckConstraint):
                texto = str(constraint.sqltext)
                if "btrim" in texto or " ~ " in texto:
                    tabela.constraints.discard(constraint)


_remover_constraints_exclusivas_do_postgres()


@pytest.fixture(scope="session", autouse=True)
def _banco_sqlite_temporario():
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture()
def db_session():
    """Sessão SQLAlchemy contra o SQLite temporário (mesmo banco usado pela API nos testes)."""
    from sqlalchemy.orm import sessionmaker
    sessao = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    try:
        yield sessao
    finally:
        sessao.close()
