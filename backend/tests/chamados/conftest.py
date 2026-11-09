"""
Fixtures dos testes de OS/visitas/pausa/custos (Backend frente A).

Roda sobre o SQLite temporário de tests/conftest.py (NUNCA contra o DATABASE_URL real). Uploads e assinaturas vão para a
pasta temporária de cada teste.
"""
import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.db.database import Base, engine, get_db
from app.main import app
from app.services import file_service
from chamados.helpers import Fluxo, Usuario, criar_cliente, criar_usuario

@pytest.fixture(autouse=True)
def _limpar_tabelas():
    with engine.begin() as conn:
        for tabela in reversed(Base.metadata.sorted_tables):
            conn.execute(tabela.delete())
    yield


@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch):
    original = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda rounds=4, prefix=b"2b": original(rounds=4, prefix=prefix))


@pytest.fixture(autouse=True)
def _diretorios_temporarios(tmp_path, monkeypatch):
    """Uploads e assinaturas vão para a pasta temporária do teste, nunca para backend/static."""
    monkeypatch.setattr(file_service, "UPLOAD_DIRECTORY", tmp_path / "uploads")
    monkeypatch.setattr(file_service, "ASSINATURA_DIRECTORY", tmp_path / "assinaturas")
    return tmp_path


@pytest.fixture()
def client():
    from sqlalchemy.orm import sessionmaker
    fabrica = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def _get_db_teste():
        sessao = fabrica()
        try:
            yield sessao
        finally:
            sessao.close()

    app.dependency_overrides[get_db] = _get_db_teste
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def db(db_session):
    return db_session


@pytest.fixture()
def admin(db) -> Usuario:
    return criar_usuario(db, "admin")


@pytest.fixture()
def tecnico(db) -> Usuario:
    return criar_usuario(db, "tecnico")


@pytest.fixture()
def outro_tecnico(db) -> Usuario:
    return criar_usuario(db, "tecnico")


@pytest.fixture()
def cliente_id(db) -> int:
    return criar_cliente(db)


@pytest.fixture()
def fluxo(client, admin, tecnico, cliente_id) -> Fluxo:
    return Fluxo(client, admin, tecnico, cliente_id)


