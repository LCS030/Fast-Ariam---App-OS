"""
Armazenamento privado (Supabase Storage) e entrega autenticada dos arquivos (SEG-09 / PR-03).

SQLite + transporte HTTP simulado: NÃO fala com o Supabase real. O comportamento contra o servidor real só é conferido
com `python scripts/testar_storage.py` (precisa de SUPABASE_URL e SUPABASE_SERVICE_KEY).
"""
import hashlib

import httpx
import pytest
from fastapi import HTTPException

from app.core import config
from app.models.servico_foto import ServicoFoto
from app.models.visita import Visita
from app.services import file_service
from app.services.storage_service import SupabaseStorage
from chamados.helpers import Fluxo, imagem


class ArmazenamentoMemoria:
    """Substituto em memória do bucket: prova que, com o Supabase, NADA é gravado no disco do servidor."""

    def __init__(self):
        self.itens = {}

    def put(self, area, nome, dados, content_type):
        assert (area, nome) not in self.itens, "sobrescrita silenciosa"
        self.itens[(area, nome)] = (dados, content_type)

    def get(self, area, nome):
        item = self.itens.get((area, nome))
        return item[0] if item else None

    def delete(self, area, nome):
        self.itens.pop((area, nome), None)


@pytest.fixture()
def bucket(monkeypatch):
    fake = ArmazenamentoMemoria()
    monkeypatch.setattr(file_service, "_ARMAZENAMENTO", fake)
    return fake


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# =====================================================================================================================
# Cliente do Supabase Storage (requisições)
# =====================================================================================================================

def _cliente(handler):
    return SupabaseStorage("https://proj.supabase.co/", "CHAVE-DE-SERVICO", "fast-ariam-privado",
                           client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_upload_vai_para_o_bucket_privado_com_chave_de_servico_e_sem_sobrescrever():
    vistos = []

    def handler(req: httpx.Request):
        vistos.append(req)
        return httpx.Response(200, json={"Key": "ok"})

    _cliente(handler).put("uploads", "chamado_1_foto.jpg", b"bytes", "image/jpeg")
    r = vistos[0]
    assert r.method == "POST"
    assert str(r.url) == "https://proj.supabase.co/storage/v1/object/fast-ariam-privado/uploads/chamado_1_foto.jpg"
    assert r.headers["authorization"] == "Bearer CHAVE-DE-SERVICO" and r.headers["apikey"] == "CHAVE-DE-SERVICO"
    assert r.headers["x-upsert"] == "false" and r.headers["content-type"] == "image/jpeg" and r.content == b"bytes"


def test_chave_nova_sb_secret_vai_so_no_apikey_e_a_antiga_jwt_nos_dois_cabecalhos():
    vistos = []

    def handler(req):
        vistos.append(req)
        return httpx.Response(200)

    nova = SupabaseStorage("https://proj.supabase.co", "sb_secret_abc123", "b", client=httpx.Client(transport=httpx.MockTransport(handler)))
    nova.put("uploads", "x.jpg", b"1", "image/jpeg")
    assert vistos[0].headers["apikey"] == "sb_secret_abc123" and "authorization" not in vistos[0].headers  # senão: Invalid JWT
    antiga = SupabaseStorage("https://proj.supabase.co", "eyJhbGciOi.payload.assinatura", "b",
                             client=httpx.Client(transport=httpx.MockTransport(handler)))
    antiga.put("uploads", "y.jpg", b"1", "image/jpeg")
    assert vistos[1].headers["apikey"] == "eyJhbGciOi.payload.assinatura"
    assert vistos[1].headers["authorization"] == "Bearer eyJhbGciOi.payload.assinatura"


def test_download_usa_o_endpoint_autenticado_e_objeto_inexistente_vira_none():
    def handler(req: httpx.Request):
        if req.url.path.endswith("existe.jpg"):
            assert "/object/authenticated/fast-ariam-privado/uploads/" in str(req.url)
            return httpx.Response(200, content=b"dados")
        if req.url.path.endswith("400.jpg"):  # o Storage costuma responder 400 com statusCode 404 no corpo
            return httpx.Response(400, json={"statusCode": "404", "error": "not_found", "message": "Object not found"})
        return httpx.Response(404, json={"error": "not_found"})

    s = _cliente(handler)
    assert s.get("uploads", "existe.jpg") == b"dados"
    assert s.get("uploads", "400.jpg") is None and s.get("uploads", "sumiu.jpg") is None


def test_remocao_e_idempotente():
    s = _cliente(lambda req: httpx.Response(404, json={"error": "not_found"}))
    s.delete("uploads", "x.jpg")  # inexistente: sem erro


def test_falha_do_storage_vira_503_sem_vazar_a_chave(caplog):
    s = _cliente(lambda req: httpx.Response(500, text="boom"))
    for operacao in (lambda: s.put("uploads", "a.jpg", b"x", "image/jpeg"), lambda: s.get("uploads", "a.jpg"),
                     lambda: s.delete("uploads", "a.jpg")):
        with pytest.raises(HTTPException) as e:
            operacao()
        assert e.value.status_code == 503 and "CHAVE-DE-SERVICO" not in str(e.value.detail)
    assert "CHAVE-DE-SERVICO" not in caplog.text

    def cai(req):
        raise httpx.ConnectError("sem rede")

    with pytest.raises(HTTPException) as e:
        _cliente(cai).get("uploads", "a.jpg")
    assert e.value.status_code == 503


@pytest.mark.parametrize("area,nome", [("uploads", "../x.jpg"), ("uploads", "a/b.jpg"), ("uploads", ""),
                                       ("outra", "x.jpg"), ("uploads", "..")])
def test_referencia_invalida_nao_chega_a_ser_requisitada(area, nome):
    chamadas = []
    s = _cliente(lambda req: chamadas.append(req) or httpx.Response(200))
    with pytest.raises(ValueError):
        s.get(area, nome)
    assert chamadas == []


def test_nome_com_caracteres_especiais_e_codificado_na_url():
    vistos = []
    _cliente(lambda req: vistos.append(req) or httpx.Response(200)).put("uploads", "a b?c.jpg", b"x", "image/jpeg")
    assert "a%20b%3Fc.jpg" in str(vistos[0].url)


# =====================================================================================================================
# Configuração
# =====================================================================================================================

def test_backend_de_armazenamento_conforme_a_configuracao():
    r = config.resolver_storage_backend
    assert r(None, None, production=False) == "local"
    assert r("https://x.supabase.co", "chave", production=False) == "supabase"
    assert r("https://x.supabase.co", "chave", production=True) == "supabase"
    with pytest.raises(ValueError, match="Supabase Storage"):
        r(None, None, production=True)  # disco local é efêmero e não é privado
    with pytest.raises(ValueError, match="JUNTAS"):
        r("https://x.supabase.co", None, production=False)
    with pytest.raises(ValueError, match="JUNTAS"):
        r(None, "chave", production=False)
    with pytest.raises(ValueError, match="https"):
        r("http://x.supabase.co", "chave", production=False)


# =====================================================================================================================
# Com o bucket: nada em disco; leitura só pela rota autenticada
# =====================================================================================================================

def test_com_o_bucket_foto_e_assinatura_nao_tocam_o_disco_do_servidor(fluxo, bucket, tmp_path):
    fluxo.ate_em_atendimento()
    r = fluxo.finalizar_atendimento()
    assert r.status_code == 200, r.text
    areas = {a for (a, _n) in bucket.itens}
    assert areas == {"uploads", "assinaturas"}
    assert not (tmp_path / "uploads").exists() and not (tmp_path / "assinaturas").exists()
    # a assinatura chega ao bucket JÁ CIFRADA (octet-stream)
    (nome_assin,) = [n for (a, n) in bucket.itens if a == "assinaturas"]
    dados, ctype = bucket.itens[("assinaturas", nome_assin)]
    assert nome_assin.endswith(".enc") and ctype == "application/octet-stream" and not dados.startswith(b"\x89PNG")


def _url_da_foto(db):
    db.expire_all()
    return db.query(ServicoFoto).first().url


def test_rota_entrega_a_foto_a_admin_e_tecnico_da_os_e_nega_aos_demais(fluxo, bucket, db, outro_tecnico):
    fluxo.ate_em_atendimento()
    url = _url_da_foto(db)
    original = bucket.get("uploads", url.rsplit("/", 1)[1])
    rota = f"/api/chamados/{fluxo.os_id}/arquivos/conteudo"
    for quem in (fluxo.tecnico, fluxo.admin):
        r = fluxo.c.get(rota, params={"url": url}, headers=quem.headers)
        assert r.status_code == 200 and r.content == original and r.headers["content-type"] == "image/jpeg"
        assert "private" in r.headers["cache-control"] and r.headers["x-content-type-options"] == "nosniff"
    assert fluxo.c.get(rota, params={"url": url}, headers=outro_tecnico.headers).status_code == 403
    assert fluxo.c.get(rota, params={"url": url}).status_code == 401


def test_rota_nao_entrega_arquivo_de_outra_os_nem_assinatura_nem_referencia_inventada(fluxo, bucket, db):
    fluxo.ate_em_atendimento()
    url = _url_da_foto(db)
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.criar_os()
    outra.criar_visita()
    # a foto é da primeira OS: pedir pela rota da outra (mesmo admin) é 404 (anti-IDOR por nome adivinhado)
    r = fluxo.c.get(f"/api/chamados/{outra.os_id}/arquivos/conteudo", params={"url": url}, headers=fluxo.admin.headers)
    assert r.status_code == 404
    rota = f"/api/chamados/{fluxo.os_id}/arquivos/conteudo"
    for ref in ("/static/uploads/inexistente.jpg", "/static/uploads/../x", "http://evil/x.jpg", "x.jpg",
                "/static/assinaturas/qualquer.enc"):
        assert fluxo.c.get(rota, params={"url": ref}, headers=fluxo.admin.headers).status_code == 404, ref
    # arquivo registrado no banco mas ausente do bucket
    bucket.delete("uploads", url.rsplit("/", 1)[1])
    assert fluxo.c.get(rota, params={"url": url}, headers=fluxo.admin.headers).status_code == 404


def test_foto_de_deslocamento_tambem_sai_pela_rota(fluxo, bucket, db):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa()
    db.expire_all()
    ida = db.get(Visita, fluxo.visita_id).foto_inicio_ida_url
    assert ida
    r = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/arquivos/conteudo", params={"url": ida}, headers=fluxo.tecnico.headers)
    assert r.status_code == 200 and r.content == bucket.get("uploads", ida.rsplit("/", 1)[1])


def test_static_nao_serve_mais_nada_nem_com_o_arquivo_no_disco(client):
    file_service.UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (file_service.UPLOAD_DIRECTORY / "publica.jpg").write_bytes(imagem(10, 10)[1])
    file_service.ASSINATURA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (file_service.ASSINATURA_DIRECTORY / "x.enc").write_bytes(b"x")
    for caminho in ("/static/uploads/publica.jpg", "/static/assinaturas/x.enc", "/static/"):
        assert client.get(caminho).status_code == 404, caminho


def test_verificacao_de_integridade_le_do_bucket(fluxo, bucket, db):
    fluxo.ate_em_atendimento()
    assert fluxo.finalizar_atendimento().status_code == 200
    ok = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/verificar-integridade", headers=fluxo.admin.headers).json()
    assert ok["estado"] == "integro", ok
    nome = db.query(ServicoFoto).first().url.rsplit("/", 1)[1]
    bucket.itens[("uploads", nome)] = (imagem(55, 66)[1], "image/jpeg")  # alguém troca o objeto no bucket
    motivos = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/verificar-integridade",
                          headers=fluxo.admin.headers).json()["visitas"][0]["motivos"]
    assert any(m.startswith("arquivo_divergente:foto_") for m in motivos)


def test_referencia_logica_rejeita_traversal_e_prefixos_errados():
    ref = file_service._referencia
    assert ref("/static/uploads/a.jpg") == ("uploads", "a.jpg")
    assert ref("/static/assinaturas/b.enc") == ("assinaturas", "b.enc")
    for ruim in (None, "", "a.jpg", "/static/uploads/", "/static/uploads/../a.jpg", "/static/uploads/x/y.jpg",
                 "/static/uploads/..", "/static/outra/a.jpg", "/static/uploads/a\\b.jpg"):
        assert ref(ruim) is None, ruim
