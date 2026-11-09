"""
Testes de autenticação, técnicos e clientes (Backend frente B).

Cobre: T-03 (parcial), T-05, T-17 (parte técnico inativo -> 401), T-23, CA-12, login com mensagem única (SEG-02),
GET /auth/me (PR-06), SEG-10 (dados bancários), SEG-11 (cliente por OS), CPF/CNPJ (PR-34), RN-06 (409), CORS (SEG-03),
guardas de ambiente (SEG-05) e configuração de custo global (PR-22/PR-33).

Todos os testes rodam no SQLite temporário definido em conftest.py (nunca no DATABASE_URL real).
"""
import itertools
import time
from datetime import date, datetime, timedelta, timezone

import bcrypt
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.db.database import engine, Base, get_db

# Trava extra: se o conftest for substituído por outro sem isolamento, estes testes se recusam a rodar.
if engine.url.get_backend_name() != "sqlite":
    pytest.exit("ABORTADO: testes de auth/tecnicos/clientes exigem SQLite temporário (veja tests/conftest.py).",
                returncode=2)

from app.main import app  # noqa: E402
from app.core import config  # noqa: E402
from app.core.security import hash_password, create_access_token, verify_password  # noqa: E402
from app.models.tecnico import Tecnico  # noqa: E402
from app.models.cliente import Cliente  # noqa: E402
from app.models.chamado import OrdemServico  # noqa: E402
from app.schemas.base_schemas import StatusChamado  # noqa: E402
from app.schemas.tecnico import cnpj_valido, formatar_cnpj, formatar_cpf  # noqa: E402
from app.core.validators import cpf_valido  # noqa: E402

SENHA = "Senha@12345"
MENSAGEM_LOGIN = "Email ou senha incorretos"
_seq = itertools.count(1)


# --- Geradores de documentos válidos -----------------------------------------------------------------------------------
def _digitos_cpf(base9: str) -> str:
    cpf = base9
    for tamanho in (9, 10):
        soma = sum(int(cpf[i]) * (tamanho + 1 - i) for i in range(tamanho))
        cpf += str((soma * 10) % 11 % 10)
    return cpf


def gerar_cpf() -> str:
    n = next(_seq)
    return formatar_cpf(_digitos_cpf(f"{n:09d}" if n % 11 else f"{n + 1:09d}"))


def _digitos_cnpj(base12: str) -> str:
    cnpj = base12
    for tamanho in (12, 13):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if tamanho == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        cnpj += str(0 if resto < 2 else 11 - resto)
    return cnpj


def gerar_cnpj() -> str:
    n = next(_seq)
    return formatar_cnpj(_digitos_cnpj(f"{n:08d}0001"))


# --- Fixtures ----------------------------------------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _bcrypt_rapido(monkeypatch):
    """Custo 4 no bcrypt só nos testes (acelera hashing); o código de produção usa o custo padrão."""
    original = bcrypt.gensalt
    monkeypatch.setattr(bcrypt, "gensalt", lambda rounds=4, prefix=b"2b": original(rounds=4, prefix=prefix))


@pytest.fixture(autouse=True)
def _limpar_tabelas():
    with engine.begin() as conn:
        for tabela in reversed(Base.metadata.sorted_tables):
            conn.execute(tabela.delete())
    yield


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


def criar_usuario(db, role="tecnico", ativo=True, senha=SENHA, email=None, nome="Fulano", com_banco=True):
    n = next(_seq)
    usuario = Tecnico(
        nome=f"{nome} {n}", cpf=gerar_cpf(), cnpj=gerar_cnpj(), telefone="(27) 99999-9999",
        email=email or f"user{n}@email.com", password_hash=hash_password(senha), role=role, is_active=ativo,
        banco="Banco X" if com_banco else None, agencia="0001" if com_banco else None,
        conta="12345-6" if com_banco else None, pix="pix-secreto@email.com" if com_banco else None,
    )
    db.add(usuario)
    db.commit()
    db.refresh(usuario)
    return usuario


def login(client, email, senha=SENHA):
    resp = client.post("/api/auth/login", data={"username": email, "password": senha})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture()
def admin(db_session):
    return criar_usuario(db_session, role="admin", nome="Admin")


@pytest.fixture()
def admin_headers(client, admin):
    return login(client, admin.email)


def payload_tecnico(**sobrescrever):
    n = next(_seq)
    base = {
        "nome": f"Técnico {n}", "cnpj": gerar_cnpj(), "cpf": gerar_cpf(), "inscricao_estadual": "ISENTO",
        "email": f"tec{n}@email.com", "telefone": "(27) 99999-9999", "password": "senha-forte",
        "role": "tecnico",
        "dados_bancarios": {"banco": "Banco X", "agencia": "0001", "conta": "12345-6", "pix": "pix@email.com"},
    }
    base.update(sobrescrever)
    return base


def payload_cliente(**sobrescrever):
    n = next(_seq)
    base = {
        "razao_social": f"Cliente {n} LTDA", "telefone": "2733334444", "endereco": "RUA A", "numero": "10",
        "bairro": "CENTRO", "cidade": "SERRA", "uf": "ES", "codigo": 1000 + n,
    }
    base.update(sobrescrever)
    return base


def criar_cliente_db(db, **kw):
    n = next(_seq)
    cli = Cliente(razao_social=f"Cli {n}", codigo=50000 + n, telefone="1", endereco="R", numero="1", bairro="B",
                  cidade="C", uf="ES", is_active=True, **kw)
    db.add(cli)
    db.commit()
    db.refresh(cli)
    return cli


def criar_os_db(db, cliente, tecnico):
    os_ = OrdemServico(id_cliente=cliente.id_cliente, id_tecnico_atribuido=tecnico.id_tecnico,
                       status=StatusChamado.AGENDADO.value, data_abertura=date.today())
    db.add(os_)
    db.commit()
    db.refresh(os_)
    return os_


# ===================================================================================================================
# Login (SEG-02, PR-21, PR-23)
# ===================================================================================================================
def test_login_sucesso_retorna_bearer_com_claims(client, db_session):
    u = criar_usuario(db_session, role="tecnico")
    resp = client.post("/api/auth/login", data={"username": u.email, "password": SENHA})
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["token_type"] == "bearer"
    claims = jwt.get_unverified_claims(corpo["access_token"])
    assert claims["sub"] == u.email
    assert claims["user_id"] == u.id_tecnico
    assert claims["role"] == "tecnico"
    assert "exp" in claims


def test_login_email_e_case_insensitive(client, db_session):
    u = criar_usuario(db_session, email="misto@email.com")
    resp = client.post("/api/auth/login", data={"username": "  MISTO@Email.COM ", "password": SENHA})
    assert resp.status_code == 200


def test_login_mensagem_unica_para_inexistente_senha_errada_e_inativo(client, db_session):
    ativo = criar_usuario(db_session)
    inativo = criar_usuario(db_session, ativo=False)
    casos = [
        {"username": "nao-existe@email.com", "password": SENHA},  # e-mail inexistente
        {"username": ativo.email, "password": "senha-errada-xyz"},  # senha errada
        {"username": inativo.email, "password": SENHA},  # inativo, senha correta
        {"username": inativo.email, "password": "senha-errada-xyz"},  # inativo, senha errada
    ]
    respostas = [client.post("/api/auth/login", data=c) for c in casos]
    for r in respostas:
        assert r.status_code == 401
        assert r.json() == {"detail": MENSAGEM_LOGIN}
    assert len({r.text for r in respostas}) == 1  # corpos idênticos


def test_login_email_inexistente_executa_bcrypt_dummy(client, monkeypatch):
    chamadas = []
    import app.api.endpoints.auth as auth_mod
    monkeypatch.setattr(auth_mod, "verify_password_dummy", lambda senha: chamadas.append(senha))
    resp = client.post("/api/auth/login", data={"username": "ninguem@email.com", "password": "qualquer"})
    assert resp.status_code == 401
    assert chamadas == ["qualquer"]


def test_login_busca_somente_pelo_email_sem_varrer_tabela(client, db_session):
    for _ in range(5):
        criar_usuario(db_session)
    alvo = criar_usuario(db_session)
    consultas = []

    from sqlalchemy import event

    def _captura(conn, cursor, statement, parameters, context, executemany):
        if "FROM tecnico" in statement:
            consultas.append(statement)

    event.listen(engine, "before_cursor_execute", _captura)
    try:
        assert client.post("/api/auth/login", data={"username": alvo.email, "password": SENHA}).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", _captura)
    assert len(consultas) == 1
    assert "WHERE" in consultas[0].upper()


def test_login_senha_maior_que_72_bytes_nao_gera_500(client, db_session):
    u = criar_usuario(db_session)
    resp = client.post("/api/auth/login", data={"username": u.email, "password": "x" * 200})
    assert resp.status_code == 401


# ===================================================================================================================
# Validação do token a cada requisição (SEG-01, PR-05, T-05, T-17, CA-12)
# ===================================================================================================================
def test_t05_ca12_token_de_tecnico_desativado_recebe_401(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    headers_tec = login(client, tec.email)
    assert client.get("/api/auth/me", headers=headers_tec).status_code == 200

    assert client.delete(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers).status_code == 204

    # mesmo token, requisição seguinte
    assert client.get("/api/auth/me", headers=headers_tec).status_code == 401
    assert client.get("/api/chamados/", headers=headers_tec).status_code == 401
    assert client.patch("/api/tecnicos/me/password", headers=headers_tec,
                        json={"old_password": SENHA, "new_password": "outra-senha-1"}).status_code == 401


def test_t17_desativar_desatribui_os_nao_finalizadas_rn08a(client, db_session, admin_headers):
    """RN-08a (aprovada): a desativação devolve a OS não finalizada a Pendente, sem técnico (cobertura completa em
    tests/chamados/test_desativacao_tecnico.py)."""
    tec = criar_usuario(db_session)
    cliente = criar_cliente_db(db_session)
    os_ = criar_os_db(db_session, cliente, tec)
    assert client.delete(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers).status_code == 204
    db_session.expire_all()
    os_db = db_session.get(OrdemServico, os_.id_os)
    assert os_db.id_tecnico_atribuido is None
    assert os_db.status == StatusChamado.PENDENTE


def test_t05_token_de_admin_desativado_recebe_401(client, db_session, admin_headers):
    outro_admin = criar_usuario(db_session, role="admin")
    headers_outro = login(client, outro_admin.email)
    assert client.delete(f"/api/tecnicos/{outro_admin.id_tecnico}", headers=admin_headers).status_code == 204
    assert client.get("/api/tecnicos/", headers=headers_outro).status_code == 401


def test_token_de_usuario_removido_do_banco_recebe_401(client, db_session):
    u = criar_usuario(db_session)
    headers = login(client, u.email)
    db_session.delete(db_session.get(Tecnico, u.id_tecnico))
    db_session.commit()
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_reativar_tecnico_restaura_o_acesso(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    headers = login(client, tec.email)
    client.delete(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers)
    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.patch(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers,
                        json={"is_active": True}).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 200


def test_role_vem_do_banco_e_nao_do_token(client, db_session):
    tec = criar_usuario(db_session, role="tecnico")
    token_forjado = create_access_token({"sub": tec.email, "user_id": tec.id_tecnico, "role": "admin"})
    resp = client.get("/api/tecnicos/", headers={"Authorization": f"Bearer {token_forjado}"})
    assert resp.status_code == 403  # token diz admin, banco diz tecnico

    # inverso: admin rebaixado no banco perde o acesso administrativo com o token antigo
    adm = criar_usuario(db_session, role="admin")
    headers = login(client, adm.email)
    assert client.get("/api/tecnicos/", headers=headers).status_code == 200
    adm_db = db_session.get(Tecnico, adm.id_tecnico)
    adm_db.role = "tecnico"
    db_session.commit()
    assert client.get("/api/tecnicos/", headers=headers).status_code == 403


def test_email_alterado_invalida_token_antigo(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    headers = login(client, tec.email)
    assert client.patch(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers,
                        json={"email": "novo-email@email.com"}).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


@pytest.mark.parametrize("cabecalho", [None, "Bearer lixo.nao.jwt", "Bearer "])
def test_token_ausente_ou_malformado_recebe_401(client, cabecalho):
    headers = {"Authorization": cabecalho} if cabecalho is not None else {}
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_token_expirado_assinatura_errada_e_alg_none_sao_rejeitados(client, db_session):
    u = criar_usuario(db_session)
    claims = {"sub": u.email, "user_id": u.id_tecnico, "role": "tecnico"}

    expirado = create_access_token(claims, expires_delta=timedelta(minutes=-5))
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {expirado}"}).status_code == 401

    outra_chave = jwt.encode({**claims, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, "outra-chave",
                             algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {outra_chave}"}).status_code == 401

    import base64
    import json as _json

    def b64(d):
        return base64.urlsafe_b64encode(_json.dumps(d).encode()).rstrip(b"=").decode()

    sem_assinatura = f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({**claims, 'exp': int(time.time()) + 300})}."
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {sem_assinatura}"}).status_code == 401

    sem_exp = jwt.encode(claims, config.SECRET_KEY, algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {sem_exp}"}).status_code == 401


def test_dependencias_de_auth_sao_sincronas():
    import inspect
    from app.core import security
    for fn in (security.get_current_user, security.get_current_active_user, security.require_admin_role,
               security.require_technician_role, security.require_role("admin")):
        assert not inspect.iscoroutinefunction(fn)


def test_require_role_generico_funciona(client, db_session):
    from app.core.security import require_role
    from fastapi import Depends, FastAPI
    mini = FastAPI()

    @mini.get("/so-tecnico")
    def so_tecnico(u=Depends(require_role("tecnico"))):
        return {"role": u["role"]}

    mini.dependency_overrides[get_db] = app.dependency_overrides[get_db]
    c = TestClient(mini)
    tec = criar_usuario(db_session, role="tecnico")
    adm = criar_usuario(db_session, role="admin")
    assert c.get("/so-tecnico", headers=login(client, tec.email)).status_code == 200
    assert c.get("/so-tecnico", headers=login(client, adm.email)).status_code == 403


# ===================================================================================================================
# GET /auth/me (PR-06) e dados bancários (SEG-10, RN-07)
# ===================================================================================================================
def test_auth_me_retorna_somente_campos_seguros(client, db_session):
    tec = criar_usuario(db_session, com_banco=True)
    resp = client.get("/api/auth/me", headers=login(client, tec.email))
    assert resp.status_code == 200
    corpo = resp.json()
    assert set(corpo) == {"id_tecnico", "nome", "email", "role", "is_active"}
    assert corpo["id_tecnico"] == tec.id_tecnico and corpo["role"] == "tecnico" and corpo["is_active"] is True
    texto = resp.text.lower()
    for proibido in ("banco", "agencia", "conta", "pix", "dados_bancarios", "password", "cpf", "cnpj"):
        assert proibido not in texto


def test_seg10_tecnico_nao_acessa_rotas_com_dados_bancarios(client, db_session):
    tec = criar_usuario(db_session, com_banco=True)
    outro = criar_usuario(db_session, com_banco=True)
    headers = login(client, tec.email)
    for resp in (
            client.get("/api/tecnicos/", headers=headers),
            client.get(f"/api/tecnicos/{tec.id_tecnico}", headers=headers),
            client.get(f"/api/tecnicos/{outro.id_tecnico}", headers=headers),
    ):
        assert resp.status_code == 403
        assert "pix-secreto" not in resp.text and "banco" not in resp.text.lower()


def test_rn07_somente_admin_altera_dados_bancarios(client, db_session, admin_headers):
    tec = criar_usuario(db_session, com_banco=True)
    headers_tec = login(client, tec.email)
    # técnico não altera nem o próprio cadastro
    assert client.patch(f"/api/tecnicos/{tec.id_tecnico}", headers=headers_tec,
                        json={"dados_bancarios": {"conta": "999"}}).status_code == 403
    # admin altera parcialmente
    resp = client.patch(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers,
                        json={"dados_bancarios": {"conta": "999-9", "pix": None}})
    assert resp.status_code == 200
    assert resp.json()["dados_bancarios"] == {"banco": "Banco X", "agencia": "0001", "conta": "999-9", "pix": None}


def test_admin_ve_dados_bancarios_mas_nunca_password_hash(client, db_session, admin_headers):
    tec = criar_usuario(db_session, com_banco=True)
    unico = client.get(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers)
    lista = client.get("/api/tecnicos/", headers=admin_headers)
    assert unico.status_code == 200 and lista.status_code == 200
    assert unico.json()["dados_bancarios"]["banco"] == "Banco X"
    assert "password" not in unico.text.lower() and "password" not in lista.text.lower()
    assert "$2b$" not in unico.text and "$2b$" not in lista.text


def test_listagem_admin_tolera_registro_antigo_sem_banco_e_telefone(client, db_session, admin_headers):
    """Registros antigos incompletos (ex.: admin do seed) não podem causar 500 na saída."""
    antigo = Tecnico(nome="Antigo", cpf="000.000.000-00", cnpj="00.000.000/0000-00", email="antigo@email.com",
                     password_hash=hash_password(SENHA), role="admin", is_active=True)
    db_session.add(antigo)
    db_session.commit()
    resp = client.get("/api/tecnicos/", headers=admin_headers)
    assert resp.status_code == 200
    item = next(t for t in resp.json() if t["email"] == "antigo@email.com")
    assert item["dados_bancarios"] is None and item["telefone"] is None


# ===================================================================================================================
# Cadastro de técnico: obrigatórios, CPF/CNPJ, unicidade (RN-06, RN-07, PR-34)
# ===================================================================================================================
def test_criar_tecnico_ok_normaliza_email_e_documentos(client, admin_headers):
    cpf = gerar_cpf()
    cnpj = gerar_cnpj()
    dados = payload_tecnico(email="  Novo.Tecnico@EMAIL.com ", cpf=cpf.replace(".", "").replace("-", ""),
                            cnpj="".join(c for c in cnpj if c.isdigit()))
    resp = client.post("/api/tecnicos/", json=dados, headers=admin_headers)
    assert resp.status_code == 201, resp.text
    corpo = resp.json()
    assert corpo["email"] == "novo.tecnico@email.com"
    assert corpo["cpf"] == cpf and corpo["cnpj"] == cnpj  # forma canônica com máscara
    assert corpo["dados_bancarios"]["banco"] == "Banco X"
    assert "password" not in resp.text.lower()
    # o novo técnico consegue logar (e-mail em minúsculas, senha com hash)
    assert client.post("/api/auth/login", data={"username": "NOVO.tecnico@email.com", "password": "senha-forte"}
                       ).status_code == 200


@pytest.mark.parametrize("campo", ["dados_bancarios", "telefone", "nome", "cnpj", "cpf", "email", "password"])
def test_criar_tecnico_campos_obrigatorios(client, admin_headers, campo):
    dados = payload_tecnico()
    dados.pop(campo)
    assert client.post("/api/tecnicos/", json=dados, headers=admin_headers).status_code == 422


@pytest.mark.parametrize("faltando", ["banco", "agencia", "conta"])
def test_criar_tecnico_dados_bancarios_exigem_banco_agencia_conta(client, admin_headers, faltando):
    dados = payload_tecnico()
    dados["dados_bancarios"].pop(faltando)
    assert client.post("/api/tecnicos/", json=dados, headers=admin_headers).status_code == 422


def test_criar_tecnico_pix_e_opcional(client, admin_headers):
    dados = payload_tecnico()
    dados["dados_bancarios"].pop("pix")
    resp = client.post("/api/tecnicos/", json=dados, headers=admin_headers)
    assert resp.status_code == 201 and resp.json()["dados_bancarios"]["pix"] is None


@pytest.mark.parametrize("cpf", ["111.111.111-11", "123.456.789-00", "123", "abc", "529.982.247-26"])
def test_criar_tecnico_cpf_invalido_422(client, admin_headers, cpf):
    resp = client.post("/api/tecnicos/", json=payload_tecnico(cpf=cpf), headers=admin_headers)
    assert resp.status_code == 422
    assert "CPF inválido" in resp.text


@pytest.mark.parametrize("cnpj", ["00.000.000/0001-00", "11.111.111/1111-11", "12.345.678/0001-00", "123"])
def test_criar_tecnico_cnpj_invalido_422(client, admin_headers, cnpj):
    resp = client.post("/api/tecnicos/", json=payload_tecnico(cnpj=cnpj), headers=admin_headers)
    assert resp.status_code == 422
    assert "CNPJ inválido" in resp.text


@pytest.mark.parametrize("senha", ["curta", "x" * 73, "        "])
def test_criar_tecnico_senha_invalida_422(client, admin_headers, senha):
    assert client.post("/api/tecnicos/", json=payload_tecnico(password=senha), headers=admin_headers
                       ).status_code == 422


def test_criar_tecnico_email_invalido_422(client, admin_headers):
    assert client.post("/api/tecnicos/", json=payload_tecnico(email="nao-e-email"), headers=admin_headers
                       ).status_code == 422


def test_criar_tecnico_email_duplicado_409_inclusive_com_outra_caixa(client, admin_headers):
    primeiro = payload_tecnico(email="duplicado@email.com")
    assert client.post("/api/tecnicos/", json=primeiro, headers=admin_headers).status_code == 201
    segundo = payload_tecnico(email="DUPLICADO@email.com")
    resp = client.post("/api/tecnicos/", json=segundo, headers=admin_headers)
    assert resp.status_code == 409
    assert "e-mail" in resp.json()["detail"].lower()


def test_criar_tecnico_cnpj_duplicado_409_mesmo_sem_mascara(client, admin_headers):
    cnpj = gerar_cnpj()
    assert client.post("/api/tecnicos/", json=payload_tecnico(cnpj=cnpj), headers=admin_headers).status_code == 201
    sem_mascara = "".join(c for c in cnpj if c.isdigit())
    resp = client.post("/api/tecnicos/", json=payload_tecnico(cnpj=sem_mascara), headers=admin_headers)
    assert resp.status_code == 409
    assert "cnpj" in resp.json()["detail"].lower()


def test_criar_tecnico_exige_admin(client, db_session):
    tec = criar_usuario(db_session)
    assert client.post("/api/tecnicos/", json=payload_tecnico(), headers=login(client, tec.email)).status_code == 403
    assert client.post("/api/tecnicos/", json=payload_tecnico()).status_code == 401


def test_criar_tecnico_erro_nao_vaza_internals(client, admin_headers):
    cnpj = gerar_cnpj()
    client.post("/api/tecnicos/", json=payload_tecnico(cnpj=cnpj), headers=admin_headers)
    resp = client.post("/api/tecnicos/", json=payload_tecnico(cnpj=cnpj), headers=admin_headers)
    texto = resp.text.lower()
    for vazamento in ("sqlalchemy", "integrityerror", "unique constraint", "insert into", "sqlite"):
        assert vazamento not in texto


# --- PATCH / DELETE de técnico -------------------------------------------------------------------------------------
def test_patch_tecnico_valida_cpf_e_nao_aceita_nulo_em_obrigatorio(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    url = f"/api/tecnicos/{tec.id_tecnico}"
    assert client.patch(url, headers=admin_headers, json={"cpf": "111.111.111-11"}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={"nome": None}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={"telefone": None}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={"dados_bancarios": {"banco": None}}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={}).status_code == 400
    ok = client.patch(url, headers=admin_headers, json={"nome": "Novo Nome", "cpf": gerar_cpf()})
    assert ok.status_code == 200 and ok.json()["nome"] == "Novo Nome"


def test_patch_tecnico_email_ou_cnpj_duplicado_409(client, db_session, admin_headers):
    a = criar_usuario(db_session)
    b = criar_usuario(db_session)
    url = f"/api/tecnicos/{b.id_tecnico}"
    assert client.patch(url, headers=admin_headers, json={"email": a.email.upper()}).status_code == 409
    assert client.patch(url, headers=admin_headers, json={"cnpj": a.cnpj}).status_code == 409
    # manter o próprio e-mail/CNPJ não é conflito
    assert client.patch(url, headers=admin_headers, json={"email": b.email, "cnpj": b.cnpj}).status_code == 200


def test_patch_e_get_tecnico_inexistente_404(client, admin_headers):
    assert client.get("/api/tecnicos/99999", headers=admin_headers).status_code == 404
    assert client.patch("/api/tecnicos/99999", headers=admin_headers, json={"nome": "x"}).status_code == 404
    assert client.delete("/api/tecnicos/99999", headers=admin_headers).status_code == 404


def test_delete_tecnico_desativacao_logica_e_idempotente(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    assert client.delete(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers).status_code == 204
    db_session.expire_all()
    assert db_session.get(Tecnico, tec.id_tecnico).is_active is False  # registro continua existindo
    assert client.delete(f"/api/tecnicos/{tec.id_tecnico}", headers=admin_headers).status_code == 204
    assert client.get("/api/tecnicos/?is_active=false", headers=admin_headers).json()[0]["id_tecnico"] == tec.id_tecnico


def test_delete_tecnico_exige_admin(client, db_session):
    a = criar_usuario(db_session)
    b = criar_usuario(db_session)
    assert client.delete(f"/api/tecnicos/{b.id_tecnico}", headers=login(client, a.email)).status_code == 403


def test_admin_nao_desativa_a_si_mesmo_nem_se_rebaixa(client, admin, admin_headers):
    url = f"/api/tecnicos/{admin.id_tecnico}"
    assert client.delete(url, headers=admin_headers).status_code == 400
    assert client.patch(url, headers=admin_headers, json={"is_active": False}).status_code == 400
    assert client.patch(url, headers=admin_headers, json={"role": "tecnico"}).status_code == 400
    # continua com acesso
    assert client.get("/api/auth/me", headers=admin_headers).status_code == 200


def test_admin_pode_desativar_outro_admin_enquanto_restar_um(client, db_session, admin_headers):
    outro = criar_usuario(db_session, role="admin")
    assert client.delete(f"/api/tecnicos/{outro.id_tecnico}", headers=admin_headers).status_code == 204


def test_sistema_nao_fica_sem_administrador_ativo(db_session, admin):
    from fastapi import HTTPException
    from app.api.endpoints.tecnicos import _garantir_admin_nao_se_remove
    from app.schemas.base_schemas import UserRole
    # defesa em profundidade: outro "chamador" tentando remover o único admin ativo
    with pytest.raises(HTTPException) as exc:
        _garantir_admin_nao_se_remove(db_session, admin, admin_logado_id=-1, novo_ativo=False,
                                      novo_role=UserRole.ADMIN)
    assert exc.value.status_code == 400


# --- Troca de senha ---------------------------------------------------------------------------------------------------
def test_troca_de_senha_ok_204_e_novo_login(client, db_session):
    u = criar_usuario(db_session)
    headers = login(client, u.email)
    resp = client.patch("/api/tecnicos/me/password", headers=headers,
                        json={"old_password": SENHA, "new_password": "nova-senha-123"})
    assert resp.status_code == 204 and resp.content == b""
    assert client.post("/api/auth/login", data={"username": u.email, "password": SENHA}).status_code == 401
    assert client.post("/api/auth/login", data={"username": u.email, "password": "nova-senha-123"}
                       ).status_code == 200


def test_troca_de_senha_exige_senha_atual_correta(client, db_session):
    u = criar_usuario(db_session)
    headers = login(client, u.email)
    resp = client.patch("/api/tecnicos/me/password", headers=headers,
                        json={"old_password": "errada", "new_password": "nova-senha-123"})
    assert resp.status_code == 400
    assert client.post("/api/auth/login", data={"username": u.email, "password": SENHA}).status_code == 200


@pytest.mark.parametrize("nova", ["curta", "x" * 73, "        "])
def test_troca_de_senha_rejeita_nova_senha_fraca_ou_longa(client, db_session, nova):
    u = criar_usuario(db_session)
    resp = client.patch("/api/tecnicos/me/password", headers=login(client, u.email),
                        json={"old_password": SENHA, "new_password": nova})
    assert resp.status_code == 422


def test_troca_de_senha_exige_autenticacao(client):
    assert client.patch("/api/tecnicos/me/password",
                        json={"old_password": "a", "new_password": "nova-senha-123"}).status_code == 401


def test_rota_me_password_e_declarada_antes_de_id():
    caminhos = [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/tecnicos")]
    assert caminhos.index("/api/tecnicos/me/password") < caminhos.index("/api/tecnicos/{tecnico_id}")


# ===================================================================================================================
# Clientes (T-23, PR-27, SEG-11)
# ===================================================================================================================
def test_t23_criar_cliente_sem_codigo_422(client, admin_headers):
    dados = payload_cliente()
    dados.pop("codigo")
    resp = client.post("/api/clientes/", json=dados, headers=admin_headers)
    assert resp.status_code == 422


def test_criar_cliente_ok_normaliza_uf(client, admin_headers):
    resp = client.post("/api/clientes/", json=payload_cliente(uf="es", codigo=777), headers=admin_headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()["uf"] == "ES" and resp.json()["codigo"] == 777


@pytest.mark.parametrize("uf", ["E", "ESS", "E1", "1", "", "  "])
def test_criar_cliente_uf_invalida_422(client, admin_headers, uf):
    assert client.post("/api/clientes/", json=payload_cliente(uf=uf), headers=admin_headers).status_code == 422


@pytest.mark.parametrize("campo", ["razao_social", "telefone", "endereco", "numero", "bairro", "cidade", "uf", "codigo"])
def test_criar_cliente_campos_obrigatorios_sdd_6_4(client, admin_headers, campo):
    dados = payload_cliente()
    dados.pop(campo)
    assert client.post("/api/clientes/", json=dados, headers=admin_headers).status_code == 422


@pytest.mark.parametrize("codigo", ["abc", 0, -1, 1.5, 99999999999])
def test_criar_cliente_codigo_deve_ser_inteiro_valido(client, admin_headers, codigo):
    assert client.post("/api/clientes/", json=payload_cliente(codigo=codigo), headers=admin_headers
                       ).status_code == 422


def test_criar_cliente_codigo_duplicado_409(client, admin_headers):
    assert client.post("/api/clientes/", json=payload_cliente(codigo=4242), headers=admin_headers).status_code == 201
    resp = client.post("/api/clientes/", json=payload_cliente(codigo=4242), headers=admin_headers)
    assert resp.status_code == 409
    assert "4242" in resp.json()["detail"]


def test_patch_cliente_codigo_duplicado_409_e_proprio_codigo_ok(client, db_session, admin_headers):
    a = criar_cliente_db(db_session)
    b = criar_cliente_db(db_session)
    url = f"/api/clientes/{b.id_cliente}"
    assert client.patch(url, headers=admin_headers, json={"codigo": a.codigo}).status_code == 409
    assert client.patch(url, headers=admin_headers, json={"codigo": b.codigo, "cidade": "VITORIA"}).status_code == 200
    assert client.patch(url, headers=admin_headers, json={"uf": None}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={"uf": "xx1"}).status_code == 422
    assert client.patch(url, headers=admin_headers, json={}).status_code == 400
    assert client.patch("/api/clientes/99999", headers=admin_headers, json={"cidade": "X"}).status_code == 404


def test_cliente_crud_exige_admin(client, db_session):
    tec = criar_usuario(db_session)
    cli = criar_cliente_db(db_session)
    headers = login(client, tec.email)
    assert client.post("/api/clientes/", json=payload_cliente(), headers=headers).status_code == 403
    assert client.get("/api/clientes/", headers=headers).status_code == 403
    assert client.patch(f"/api/clientes/{cli.id_cliente}", json={"cidade": "X"}, headers=headers).status_code == 403
    assert client.delete(f"/api/clientes/{cli.id_cliente}", headers=headers).status_code == 403


def test_delete_cliente_e_desativacao_logica(client, db_session, admin_headers):
    cli = criar_cliente_db(db_session)
    assert client.delete(f"/api/clientes/{cli.id_cliente}", headers=admin_headers).status_code == 204
    resp = client.get(f"/api/clientes/{cli.id_cliente}", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()["is_active"] is False
    assert client.delete("/api/clientes/99999", headers=admin_headers).status_code == 404


def test_listagem_de_clientes_tolera_registro_antigo_incompleto(client, db_session, admin_headers):
    db_session.add(Cliente(razao_social="Legado", codigo=31337, uf="ES"))
    db_session.commit()
    resp = client.get("/api/clientes/", headers=admin_headers)
    assert resp.status_code == 200 and resp.json()[0]["endereco"] is None


def test_seg11_get_cliente_admin_e_tecnico_com_os_atribuida(client, db_session, admin_headers):
    tec = criar_usuario(db_session)
    cli = criar_cliente_db(db_session)
    criar_os_db(db_session, cli, tec)
    assert client.get(f"/api/clientes/{cli.id_cliente}", headers=admin_headers).status_code == 200
    resp = client.get(f"/api/clientes/{cli.id_cliente}", headers=login(client, tec.email))
    assert resp.status_code == 200 and resp.json()["id_cliente"] == cli.id_cliente


def test_seg11_tecnico_sem_os_do_cliente_recebe_403(client, db_session):
    tec = criar_usuario(db_session)
    outro_tec = criar_usuario(db_session)
    cli_dele = criar_cliente_db(db_session)
    cli_de_outro = criar_cliente_db(db_session)
    criar_os_db(db_session, cli_dele, tec)
    criar_os_db(db_session, cli_de_outro, outro_tec)
    headers = login(client, tec.email)
    assert client.get(f"/api/clientes/{cli_de_outro.id_cliente}", headers=headers).status_code == 403
    # id inexistente também 403: não revela quais ids existem
    assert client.get("/api/clientes/99999", headers=headers).status_code == 403


def test_seg11_os_cancelada_nao_da_acesso_ao_cliente(client, db_session):
    tec = criar_usuario(db_session)
    cli = criar_cliente_db(db_session)
    os_ = criar_os_db(db_session, cli, tec)
    os_.is_cancelled = True
    os_.motivo_cancelamento = "cancelada pelo cliente"
    db_session.commit()
    assert client.get(f"/api/clientes/{cli.id_cliente}", headers=login(client, tec.email)).status_code == 403


def test_get_cliente_inexistente_admin_404_e_sem_token_401(client, admin_headers):
    assert client.get("/api/clientes/99999", headers=admin_headers).status_code == 404
    assert client.get("/api/clientes/1").status_code == 401


# ===================================================================================================================
# T-03 (parcial): permissão cruzada entre técnicos em OS (endpoint de chamados é do Backend A)
# ===================================================================================================================
def test_t03_parcial_tecnico2_nao_le_os_do_tecnico1(client, db_session):
    t1 = criar_usuario(db_session)
    t2 = criar_usuario(db_session)
    cli = criar_cliente_db(db_session)
    os_ = criar_os_db(db_session, cli, t1)
    resp = client.get(f"/api/chamados/{os_.id_os}", headers=login(client, t2.email))
    assert resp.status_code == 403


# ===================================================================================================================
# Validadores CPF / CNPJ (PR-34)
# ===================================================================================================================
@pytest.mark.parametrize("cpf,esperado", [
    ("529.982.247-25", True), ("52998224725", True), ("111.111.111-11", False), ("000.000.000-00", False),
    ("529.982.247-26", False), ("1234567890", False), ("", False), ("abc.def.ghi-jk", False),
])
def test_cpf_valido(cpf, esperado):
    assert cpf_valido(cpf) is esperado


@pytest.mark.parametrize("cnpj,esperado", [
    ("11.222.333/0001-81", True), ("11222333000181", True), ("00.000.000/0000-00", False),
    ("11.111.111/1111-11", False), ("11.222.333/0001-82", False), ("123", False), ("", False),
])
def test_cnpj_valido(cnpj, esperado):
    assert cnpj_valido(cnpj) is esperado


def test_formatadores_geram_forma_canonica():
    assert formatar_cpf("52998224725") == "529.982.247-25"
    assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"
    with pytest.raises(ValueError, match="CPF inválido"):
        formatar_cpf("11111111111")
    with pytest.raises(ValueError, match="CNPJ inválido"):
        formatar_cnpj("11111111111111")


# ===================================================================================================================
# CORS (SEG-03), configuração, custo global e guardas de ambiente (SEG-05, PR-19, PR-22, PR-33)
# ===================================================================================================================
def test_cors_origem_permitida_e_bloqueada(client):
    permitido = client.options("/api/auth/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert permitido.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bloqueado = client.options("/api/auth/login", headers={
        "Origin": "https://site-malicioso.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in bloqueado.headers


def test_cors_origins_parse():
    assert config.parse_cors_origins("https://a.com, https://b.com/ ,") == ["https://a.com", "https://b.com"]
    assert config.parse_cors_origins("") == config.DEFAULT_DEV_CORS_ORIGINS
    assert config.parse_cors_origins(None) == config.DEFAULT_DEV_CORS_ORIGINS
    with pytest.raises(ValueError):
        config.parse_cors_origins("*")
    with pytest.raises(ValueError):
        config.parse_cors_origins("https://a.com,*")
    with pytest.raises(ValueError):
        config.parse_cors_origins("", production=True)  # obrigatória em produção
    assert config.parse_cors_origins("https://painel.com", production=True) == ["https://painel.com"]


def test_auto_create_tables_so_em_dev_e_test():
    assert config.auto_create_tables_enabled(None, production=False) is False
    assert config.auto_create_tables_enabled("false", production=True) is False
    assert config.auto_create_tables_enabled("true", production=False) is True
    with pytest.raises(ValueError):
        config.auto_create_tables_enabled("true", production=True)


def test_custo_global_sem_ajudante_nem_montagem_nem_rota_por_tecnico():
    assert set(config.VALORES_ASSISTENCIA) == {
        "PRIMEIRA_HORA_TECNICO", "HORA_TECNICO", "TEMPO_DESLOCAMENTO_TECNICO", "QUILOMETRAGEM"}
    assert not hasattr(config, "VALORES_MONTAGEM")
    caminhos = [getattr(r, "path", "") for r in app.routes]
    assert not any("configuracao-custo" in c for c in caminhos)


def test_secret_key_e_algoritmo_vem_do_ambiente():
    assert config.SECRET_KEY == "chave-de-teste-nao-usar-em-producao-0123456789abcdef"
    assert config.ALGORITHM == "HS256"


def test_resetar_banco_recusa_producao_e_exige_confirmacao():
    from resetar_banco import validar_reset, ResetBloqueado
    local = "postgresql+psycopg2://u:p@localhost:5432/fast_dev"
    remoto = "postgresql+psycopg2://u:p@db.supabase.co:5432/postgres"

    with pytest.raises(ResetBloqueado, match="production"):
        validar_reset("production", local, yes=True, allow_remote=True)
    with pytest.raises(ResetBloqueado):
        validar_reset("PROD", local, yes=True, allow_remote=True)
    with pytest.raises(ResetBloqueado, match="DATABASE_URL"):
        validar_reset("development", None, yes=True, allow_remote=False)
    with pytest.raises(ResetBloqueado, match="remoto"):
        validar_reset("development", remoto, yes=True, allow_remote=False)
    # confirmação digitada errada
    with pytest.raises(ResetBloqueado):
        validar_reset("development", local, yes=False, allow_remote=False, pedir_confirmacao=lambda _: "outro")
    # confirmação correta (nome do banco) e --yes
    assert validar_reset("development", local, yes=False, allow_remote=False,
                         pedir_confirmacao=lambda _: "fast_dev") == "fast_dev"
    assert validar_reset("development", local, yes=True, allow_remote=False) == "fast_dev"
    assert validar_reset("development", remoto, yes=True, allow_remote=True) == "postgres"


def test_resetar_banco_main_recusa_com_env_production(monkeypatch, capsys):
    import resetar_banco
    import app.core.config as cfg
    monkeypatch.setattr(cfg, "ENV", "production")
    assert resetar_banco.main(["--yes", "--allow-remote"]) == 1
    assert "production" in capsys.readouterr().err


# ===================================================================================================================
# seed.py (sem senha fixa)
# ===================================================================================================================
def test_seed_cria_admin_com_senha_do_ambiente_sem_duplicar(monkeypatch, db_session, capsys):
    import seed
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "Seed.Admin@Email.com")
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", "senha-do-seed-1")
    seed.semear_banco()
    seed.semear_banco()  # idempotente
    admins = db_session.query(Tecnico).filter(Tecnico.email == "seed.admin@email.com").all()
    assert len(admins) == 1
    assert admins[0].role == "admin" and admins[0].is_active
    assert verify_password("senha-do-seed-1", admins[0].password_hash)
    assert "senha-do-seed-1" not in capsys.readouterr().out  # senha informada pelo operador não é reexibida


def test_seed_sem_senha_gera_aleatoria_e_nao_usa_admin123(monkeypatch, db_session, capsys):
    import seed
    monkeypatch.setenv("SEED_ADMIN_EMAIL", "gerada@email.com")
    monkeypatch.delenv("SEED_ADMIN_PASSWORD", raising=False)
    seed.semear_banco()
    admin_db = db_session.query(Tecnico).filter(Tecnico.email == "gerada@email.com").one()
    assert not verify_password("admin123", admin_db.password_hash)
    saida = capsys.readouterr().out
    assert "Senha inicial" in saida
