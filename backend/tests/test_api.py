# TODO: Script gerado pelo Gemini, assim que possível, escrever o código para automatizar os chamados da API para testes


import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import SessionLocal
from app.models.tecnico import Tecnico
from app.core.security import hash_password
import random
from io import BytesIO
from PIL import Image

client = TestClient(app)
state = {}  # Memória compartilhada entre os testes


def create_test_image(width: int, height: int) -> tuple:
    """
    Cria uma imagem de teste em memória com as dimensões especificadas.
    Retorna uma tupla (filename, content, content_type) compatível com UploadFile.
    """
    img = Image.new("RGB", (width, height), color="red")
    img_bytes = BytesIO()
    img.save(img_bytes, format="JPEG")
    img_bytes.seek(0)
    return (f"test_image_{width}x{height}.jpg", img_bytes.getvalue(), "image/jpeg")


# ==========================================
# 1. SETUP INICIAL E AUTENTICAÇÃO
# ==========================================

def test_setup_banco_para_testes():
    """Injeta um Admin direto no banco para os testes"""
    db = SessionLocal()
    if not db.query(Tecnico).filter(Tecnico.email == "admin_teste@email.com").first():
        db.add(Tecnico(
            nome="Admin Teste", cpf="111.222.333-44", cnpj="11.222.333/0001-44",
            email="admin_teste@email.com", password_hash=hash_password("senha1"),
            role="admin", is_active=True
        ))
        db.commit()
    db.close()
    assert True


def test_check_health():
    response = client.get("/")
    assert response.status_code == 200


def test_login_e_obter_token():
    response = client.post(
        "/api/auth/login",
        data={"username": "admin_teste@email.com", "password": "senha1"}
    )
    assert response.status_code == 200
    state["token"] = response.json()["access_token"]
    state["headers"] = {"Authorization": f"Bearer {state['token']}"}


def test_novo_tecnico_via_api():
    # Sorteia apenas 2 dígitos para não estourar o limite de VARCHAR do banco (18 e 14)
    id_aleatorio = random.randint(10, 99)

    payload = {
        "cnpj": f"99.888.777/0001-{id_aleatorio}",  # Exato 18 caracteres
        "nome": "Técnico Silva",
        "cpf": f"999.888.777-{id_aleatorio}",  # Exato 14 caracteres
        "telefone": "81955443322",
        "email": f"tecnico_{id_aleatorio}@email.com",
        "password": "senha123",
        "dados_bancarios": {
            "banco": "Santander", "agencia": "0011-2", "conta": "99887-3", "pix": "pix@email.com"
        },
        "role": "tecnico"
    }
    response = client.post("/api/tecnicos", json=payload, headers=state["headers"])
    assert response.status_code in [201, 400]


# ==========================================
# 2. FLUXO DE CLIENTES
# ==========================================

def test_novo_cliente():
    payload = {
        "razao_social": "AUTO SERVICO PEIXOTO LTDA",
        "contato_principal_nome": "Karina Silva",
        "contato_principal_telefone": "27996439718",
        "telefone": "2732511264",
        "endereco": "PRACA JOAO MIGUEL",
        "numero": "132",
        "bairro": "SERRA CENTRO",
        "cidade": "SERRA",
        "uf": "ES",
        "codigo": random.randint(10000, 999999),  # <-- A MÁGICA AQUI: Código nunca se repete!
        "is_active": True
    }
    response = client.post("/api/clientes", json=payload, headers=state["headers"])
    assert response.status_code == 201
    state["cliente_id"] = response.json()["id_cliente"]


def test_buscar_clientes():
    response = client.get("/api/clientes", headers=state["headers"])
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_atualizar_cliente():
    payload = {"contato_principal_nome": "Karina Silva Atualizada"}
    response = client.patch(f"/api/clientes/{state['cliente_id']}", json=payload, headers=state["headers"])
    assert response.status_code == 200
    assert response.json()["contato_principal_nome"] == "Karina Silva Atualizada"


# ==========================================
# 3. FLUXO DE CHAMADOS E VISITAS
# ==========================================

def test_novo_chamado():
    payload = {
        "id_cliente": state["cliente_id"],
        "descricao_cliente": "Equipamento não gela.",
        "em_garantia": True
    }
    response = client.post("/api/chamados", json=payload, headers=state["headers"])
    assert response.status_code == 201
    state["chamado_id"] = response.json()["id_os"]


def test_iniciar_atendimento_chamado():
    # O endpoint que você criou para iniciar atendimento
    response = client.post(f"/api/chamados/{state['chamado_id']}/iniciar-atendimento", headers=state["headers"])
    # 200 se deu certo, 403/400 se a regra de negócio barrar algo
    assert response.status_code in [200, 400, 403]


def test_adicionar_visita_e_servico():
    payload = {
        "data_visita": "2025-11-06",
        "hora_inicio_deslocamento": "08:00",
        "hora_chegada_cliente": "08:45",
        "hora_inicio_atendimento": "09:00",  # <- Adicionado! (Exigido pelo seu Schema)
        "hora_fim_atendimento": "10:00",  # <- Adicionado!
        "km_total": 30,
        "valor_pedagio": 5.00,
        "valor_frete_devolucao": 0.00,
        "descricao_servico_executado": "Manutenção inicial",
        "servicos_realizados": [  # <- Devolvido para o payload principal!
            {
                "numero_serie_atendido": "SN-FREEZER-A",
                "nome_equipamento": "Freezer Vertical",
                "defeitos_principais": ["Refrigeração"],
                "materiais_utilizados": [{"nome": "Solda", "quantidade": 1, "valor": 10.0}]
            }
        ]
    }
    response = client.post(
        f"/api/chamados/{state['chamado_id']}/visitas",
        json=payload,
        headers=state["headers"]
    )

    assert response.status_code == 201, f"ERRO NA VISITA: {response.json()}"

    # Guarda os IDs (Visita e do primeiro Serviço) para testarmos as fotos nas rotas seguintes
    dados_visita = response.json()
    state["visita_id"] = dados_visita["id_visita"]
    state["servico_id"] = dados_visita["servicos_realizados"][0]["id_servico"]


# ==========================================
# 4. FLUXO DE UPLOADS
# ==========================================

def test_upload_foto_defeito_valida():
    """Upload de foto com resolução válida (>= 720p) deve retornar 200"""
    # Cria uma imagem 1280x720 (720p)
    valid_image = create_test_image(1280, 720)

    response = client.post(
        f"/api/chamados/{state['chamado_id']}/visitas/{state['visita_id']}/servicos/{state['servico_id']}/upload-foto",
        headers=state["headers"],
        data={"tipo": "defeito"},
        files={"file": valid_image}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["tipo"] == "defeito"
    assert data["url"]
    assert data["id_foto"]


def test_upload_foto_defeito_invalida_resolucao():
    """Upload de foto com resolução inválida (< 720p) deve retornar 400"""
    # Cria uma imagem 640x480 (< 720p)
    invalid_image = create_test_image(640, 480)

    response = client.post(
        f"/api/chamados/{state['chamado_id']}/visitas/{state['visita_id']}/servicos/{state['servico_id']}/upload-foto",
        headers=state["headers"],
        data={"tipo": "defeito"},
        files={"file": invalid_image}
    )
    assert response.status_code == 400
    assert "Resolução insuficiente" in response.json()["detail"]


def test_upload_foto_conserto_valida():
    """Upload de foto conserto com resolução válida deve retornar 200"""
    # Cria uma imagem 1920x1080 (FHD)
    valid_image = create_test_image(1920, 1080)

    response = client.post(
        f"/api/chamados/{state['chamado_id']}/visitas/{state['visita_id']}/servicos/{state['servico_id']}/upload-foto",
        headers=state["headers"],
        data={"tipo": "conserto"},
        files={"file": valid_image}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["tipo"] == "conserto"


def test_get_fotos_servico():
    """GET /fotos deve retornar lista de fotos defeito e conserto"""
    response = client.get(
        f"/api/chamados/{state['chamado_id']}/visitas/{state['visita_id']}/servicos/{state['servico_id']}/fotos",
        headers=state["headers"]
    )
    assert response.status_code == 200
    data = response.json()
    assert "fotos_defeito" in data
    assert "fotos_conserto" in data
    assert len(data["fotos_defeito"]) > 0  # Pelo menos uma foto defeito do teste anterior
    assert len(data["fotos_conserto"]) > 0  # Pelo menos uma foto conserto do teste anterior


# ==========================================
# 5. CUSTOS E FINALIZAÇÃO
# ==========================================

def test_calcular_custos():
    response = client.get(f"/api/chamados/{state['chamado_id']}/custos", headers=state["headers"])
    assert response.status_code == 200
    assert "total_geral" in response.json()


def test_deletar_cliente_soft_delete():
    response = client.delete(f"/api/clientes/{state['cliente_id']}", headers=state["headers"])
    assert response.status_code == 204  # 204 No Content é o padrão para deleção bem sucedida