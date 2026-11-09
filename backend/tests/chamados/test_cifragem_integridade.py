"""
Confidencialidade e Integridade (AES-256-GCM, SHA-256 dos arquivos, selo HMAC da visita, assinatura cifrada, TLS).

Roda no SQLite temporário. Isto NÃO verifica nada em PostgreSQL/Supabase: os controles SEG só podem ser marcados como
"verificados" depois de executados contra o PostgreSQL real.
"""
import base64
import hashlib
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core import config, crypto
from app.core.crypto import ErroDecifragem
from app.db.database import engine
from app.models.log_acao import LogAcao
from app.models.servico_foto import ServicoFoto
from app.models.tecnico import Tecnico
from app.models.visita import Visita
from app.services import file_service
from chamados.helpers import CPF_VALIDO, CPF_VALIDO_DIGITOS, Fluxo, assinatura_b64, criar_usuario, imagem


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _bruto(sql: str, **params):
    with engine.connect() as conn:
        return conn.execute(text(sql), params).fetchall()


def _finalizar(fluxo: Fluxo) -> dict:
    """OS pronta: ida, atendimento, conserto, assinatura (selo gravado). Retorna o corpo de finalizar-atendimento."""
    fluxo.ate_em_atendimento()
    r = fluxo.finalizar_atendimento(cpf=CPF_VALIDO, nome="Maria Gerente")
    assert r.status_code == 200, r.text
    return r.json()


def _verificar(fluxo: Fluxo, headers=None):
    return fluxo.c.get(f"/api/chamados/{fluxo.os_id}/verificar-integridade", headers=headers or fluxo.admin.headers)


# =====================================================================================================================
# Cifragem AES-256-GCM
# =====================================================================================================================

def test_cifrar_ida_e_volta_com_prefixo_e_nonce_diferente_a_cada_vez():
    a, b = crypto.cifrar("529.982.247-25", "tecnico.cpf"), crypto.cifrar("529.982.247-25", "tecnico.cpf")
    assert a.startswith("enc1:") and b.startswith("enc1:") and a != b  # nonce aleatório novo por cifragem
    assert "529" not in a
    assert crypto.decifrar(a, "tecnico.cpf") == crypto.decifrar(b, "tecnico.cpf") == "529.982.247-25"


def test_decifrar_falha_se_adulterado_se_de_outro_contexto_ou_sem_prefixo():
    valor = crypto.cifrar("segredo", "tecnico.pix")
    bruto = bytearray(base64.b64decode(valor[len("enc1:"):]))
    bruto[-1] ^= 0x01  # um bit na tag de autenticação
    adulterado = "enc1:" + base64.b64encode(bytes(bruto)).decode()
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(adulterado, "tecnico.pix")
    with pytest.raises(ErroDecifragem):  # mesmo valor colado em OUTRA coluna não abre (AAD = contexto)
        crypto.decifrar(valor, "tecnico.conta")
    with pytest.raises(ErroDecifragem):
        crypto.decifrar("segredo", "tecnico.pix")


def test_bytes_cifrados_ida_e_volta_e_contexto():
    dados = b"\x89PNG qualquer coisa" * 10
    cif = crypto.cifrar_bytes(dados, "arquivo.assinatura")
    assert dados not in cif and crypto.decifrar_bytes(cif, "arquivo.assinatura") == dados
    with pytest.raises(ErroDecifragem):
        crypto.decifrar_bytes(cif, "outro.contexto")


def test_indice_cego_e_deterministico_e_depende_do_contexto():
    a = crypto.indice_cego("11222333000181", "tecnico.cnpj")
    assert a == crypto.indice_cego("11222333000181", "tecnico.cnpj") and len(a) == 64
    assert a != crypto.indice_cego("11222333000182", "tecnico.cnpj")
    assert a != crypto.indice_cego("11222333000181", "outro.campo")
    assert crypto.indice_cego(None, "tecnico.cnpj") is None


def test_tecnico_e_gravado_cifrado_no_banco_e_lido_em_claro_pela_api(db, client, admin):
    from tests.test_auth_tecnicos_clientes import payload_tecnico  # noqa: PLC0415
    corpo = payload_tecnico()
    r = client.post("/api/tecnicos/", json=corpo, headers=admin.headers)
    assert r.status_code == 201, r.text
    assert r.json()["cpf"] == corpo["cpf"]  # a API devolve em claro
    linha = _bruto("SELECT cpf, cnpj, cnpj_idx, telefone, banco, agencia, conta, pix FROM tecnico WHERE id_tecnico=:i",
                   i=r.json()["id_tecnico"])[0]
    cpf, cnpj, cnpj_idx, telefone, banco, agencia, conta, pix = linha
    for campo in (cpf, cnpj, telefone, banco, agencia, conta, pix):
        assert campo.startswith("enc1:")
    assert corpo["cpf"] not in cpf and "pix@email.com" not in pix and "99999" not in telefone
    digitos = "".join(c for c in corpo["cnpj"] if c.isdigit())
    assert len(cnpj_idx) == 64 and digitos not in cnpj_idx  # índice cego, não o CNPJ


def test_cnpj_duplicado_e_barrado_pelo_indice_cego_mesmo_com_mascara_diferente(client, admin):
    from tests.test_auth_tecnicos_clientes import payload_tecnico  # noqa: PLC0415
    base = payload_tecnico()
    assert client.post("/api/tecnicos/", json=base, headers=admin.headers).status_code == 201
    digitos = "".join(c for c in base["cnpj"] if c.isdigit())
    outro = payload_tecnico(cnpj=digitos)  # mesmo CNPJ, sem máscara
    r = client.post("/api/tecnicos/", json=outro, headers=admin.headers)
    assert r.status_code == 409, r.text


def test_valor_cifrado_adulterado_no_banco_falha_na_leitura(db, tecnico):
    atual = _bruto("SELECT cpf FROM tecnico WHERE id_tecnico=:i", i=tecnico.id)[0][0]
    bruto = bytearray(base64.b64decode(atual[len("enc1:"):]))
    bruto[15] ^= 0xFF
    with engine.begin() as conn:
        conn.execute(text("UPDATE tecnico SET cpf=:v WHERE id_tecnico=:i"),
                     {"v": "enc1:" + base64.b64encode(bytes(bruto)).decode(), "i": tecnico.id})
    db.expire_all()
    with pytest.raises(ErroDecifragem):
        db.get(Tecnico, tecnico.id).cpf


def test_texto_puro_em_coluna_cifrada_e_erro_ou_legado_conforme_a_chave(db, tecnico, monkeypatch):
    with engine.begin() as conn:
        conn.execute(text("UPDATE tecnico SET cpf='111.222.333-96' WHERE id_tecnico=:i"), {"i": tecnico.id})
    db.expire_all()
    with pytest.raises(ErroDecifragem):  # padrão dos testes: legado desligado => texto puro é tratado como adulteração
        db.get(Tecnico, tecnico.id).cpf
    monkeypatch.setattr(config, "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT", True)  # fase de transição da migração
    db.expire_all()
    assert db.get(Tecnico, tecnico.id).cpf == "111.222.333-96"


def test_cpf_do_cliente_na_visita_fica_cifrado_no_banco(fluxo, db):
    _finalizar(fluxo)
    bruto = _bruto("SELECT documento_cliente FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0][0]
    assert bruto.startswith("enc1:") and CPF_VALIDO_DIGITOS not in bruto
    db.expire_all()
    assert db.get(Visita, fluxo.visita_id).documento_cliente == CPF_VALIDO_DIGITOS


# =====================================================================================================================
# Chaves
# =====================================================================================================================

def test_chaves_exigem_base64_de_32_bytes_e_existir(monkeypatch):
    monkeypatch.setenv("INDEX_KEY", base64.b64encode(b"curta").decode())
    with pytest.raises(ValueError, match="32 bytes"):
        config._chave_32_bytes("INDEX_KEY")
    monkeypatch.setenv("INDEX_KEY", "isso não é base64!!")
    with pytest.raises(ValueError, match="base64"):
        config._chave_32_bytes("INDEX_KEY")
    monkeypatch.delenv("INDEX_KEY")
    with pytest.raises(ValueError, match="não definida"):
        config._chave_32_bytes("INDEX_KEY")
    assert len({config.DATA_ENCRYPTION_KEY, config.INDEX_KEY, config.INTEGRITY_KEY}) == 3


# =====================================================================================================================
# SHA-256 dos arquivos
# =====================================================================================================================

def test_upload_com_hash_correto_grava_sha256_e_hash_errado_da_422_sem_gravar_nada(fluxo, db, tmp_path):
    fluxo.ate_em_atendimento()
    sid = fluxo.servicos()[0]["id_servico"]
    nome, dados, mime = imagem(300, 200)
    url = fluxo.url(f"servicos/{sid}/upload-foto")
    antes = len(list((tmp_path / "uploads").glob("*"))) if (tmp_path / "uploads").exists() else 0

    ruim = fluxo.c.post(url, headers=fluxo.tecnico.headers, data={"tipo": "defeito", "sha256": "0" * 64},
                        files={"file": (nome, dados, mime)})
    assert ruim.status_code == 422 and "hash divergente" in ruim.json()["detail"]
    assert ruim.json()["codigo"] == "HASH_DIVERGENTE"  # código estável: o app repete o envio em vez de descartar
    invalido = fluxo.c.post(url, headers=fluxo.tecnico.headers, data={"tipo": "defeito", "sha256": "xyz"},
                            files={"file": (nome, dados, mime)})
    assert invalido.status_code == 422
    assert (len(list((tmp_path / "uploads").glob("*"))) if (tmp_path / "uploads").exists() else 0) == antes

    ok = fluxo.c.post(url, headers=fluxo.tecnico.headers, data={"tipo": "defeito", "sha256": _sha(dados).upper()},
                      files={"file": (nome, dados, mime)})
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert db.get(ServicoFoto, ok.json()["id_foto"]).sha256 == _sha(dados)


def test_sem_hash_o_servidor_calcula_e_grava_o_proprio(fluxo, db):
    fluxo.ate_em_atendimento()
    r = fluxo.foto_servico("defeito")
    assert r.status_code == 200
    db.expire_all()
    foto = db.get(ServicoFoto, r.json()["id_foto"])
    caminho = file_service.UPLOAD_DIRECTORY / foto.url.rsplit("/", 1)[1]
    assert foto.sha256 == _sha(caminho.read_bytes())


def test_hash_da_origem_obrigatorio_quando_a_chave_esta_ligada(fluxo, monkeypatch):
    fluxo.ate_em_atendimento()
    monkeypatch.setattr(config, "SHA256_ORIGEM_OBRIGATORIO", True)
    r = fluxo.foto_servico("defeito")
    assert r.status_code == 422 and "sha256" in r.json()["detail"].lower()


def test_hash_do_deslocamento_vai_para_arquivos_sha256_da_visita(fluxo, db):
    fluxo.criar_os()
    fluxo.criar_visita()
    assert fluxo.iniciar("ida", 1000).status_code == 200
    nome, dados, mime = imagem(300, 200)
    r = fluxo.c.post(fluxo.url("upload-deslocamento"), headers=fluxo.tecnico.headers,
                     data={"tipo": "ida", "momento": "inicio", "sha256": _sha(dados)}, files={"file": (nome, dados, mime)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Visita, fluxo.visita_id).arquivos_sha256 == {"foto_inicio_ida_url": _sha(dados)}


def test_assinatura_hash_divergente_422_e_correto_grava_hash_dos_bytes_originais(fluxo, db):
    fluxo.ate_em_atendimento()
    fluxo.conserto_completo(estrito=True)
    b64 = assinatura_b64()
    puro = base64.b64decode(b64.split(",", 1)[1])
    base = {"nome_cliente": "Maria", "documento_cliente": CPF_VALIDO, "assinatura_base64": b64}
    r = fluxo.post("finalizar-atendimento", {**base, "assinatura_sha256": "a" * 64})
    assert r.status_code == 422 and "hash" in r.json()["detail"].lower()
    ok = fluxo.post("finalizar-atendimento", {**base, "assinatura_sha256": _sha(puro)})
    assert ok.status_code == 200, ok.text
    db.expire_all()
    assert db.get(Visita, fluxo.visita_id).assinatura_sha256 == _sha(puro)  # hash do ORIGINAL, antes de cifrar


def test_sync_arquivo_hash_divergente_422_correto_grava_e_reenvio_com_outro_conteudo_409(fluxo):
    from chamados.test_sync import _arquivo  # noqa: PLC0415
    fluxo.criar_os()
    fluxo.criar_visita()
    nome, dados, mime = imagem(300, 200)

    def enviar(cfid, sha, conteudo=dados):
        return fluxo.c.post("/api/sync/arquivos", headers=fluxo.tecnico.headers,
                            data={"client_file_id": cfid, "tipo_arquivo": "foto_defeito", "id_os": fluxo.os_id,
                                  "id_visita": fluxo.visita_id, "sha256": sha}, files={"file": (nome, conteudo, mime)})

    cfid = str(uuid.uuid4())
    assert enviar(cfid, "1" * 64).status_code == 422
    ok = enviar(cfid, _sha(dados))
    assert ok.status_code == 200 and ok.json()["sha256"] == _sha(dados) and ok.json()["resultado"] == "aplicado"
    igual = enviar(cfid, _sha(dados))
    assert igual.json()["resultado"] == "duplicado"
    _, outro_dado, _ = imagem(310, 210)
    troca = enviar(cfid, _sha(outro_dado), outro_dado)  # mesmo client_file_id, conteúdo diferente
    assert troca.status_code == 409
    _ = _arquivo  # helper importado só para garantir que o módulo de sync carrega junto


# =====================================================================================================================
# Selo de integridade
# =====================================================================================================================

def test_finalizar_atendimento_grava_selo_e_verificacao_da_integro(fluxo, db):
    _finalizar(fluxo)
    db.expire_all()
    v = db.get(Visita, fluxo.visita_id)
    assert len(v.selo_integridade) == 64 and v.selo_versao == 1
    r = _verificar(fluxo)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["estado"] == "integro" and corpo["visitas"][0]["estado"] == "integro" and corpo["visitas"][0]["motivos"] == []
    acoes = [a.acao for a in db.query(LogAcao).filter(LogAcao.id_os == fluxo.os_id).all()]
    assert "INTEGRIDADE_VERIFICADA" in acoes


def test_verificar_integridade_so_para_admin(fluxo, outro_tecnico):
    _finalizar(fluxo)
    assert _verificar(fluxo, headers=fluxo.tecnico.headers).status_code == 403
    assert _verificar(fluxo, headers=outro_tecnico.headers).status_code == 403
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}/verificar-integridade").status_code == 401


def test_alterar_campo_direto_no_banco_e_acusado_como_adulterado(fluxo, db):
    _finalizar(fluxo)
    with engine.begin() as conn:  # equivale a editar a linha no painel do Supabase
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura='Fraudador' WHERE id_visita=:i"), {"i": fluxo.visita_id})
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "adulterado" and "selo_divergente" in corpo["visitas"][0]["motivos"]


def test_alterar_km_da_ida_ou_defeito_tambem_e_acusado(fluxo):
    _finalizar(fluxo)
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET km_fim_ida=km_fim_ida+500 WHERE id_visita=:i"), {"i": fluxo.visita_id})
    assert _verificar(fluxo).json()["estado"] == "adulterado"


def test_trocar_arquivo_de_foto_em_disco_e_acusado_mesmo_sem_mexer_no_banco(fluxo, db):
    _finalizar(fluxo)
    foto = db.query(ServicoFoto).first()
    caminho = file_service.UPLOAD_DIRECTORY / foto.url.rsplit("/", 1)[1]
    caminho.write_bytes(imagem(321, 123)[1])  # outra imagem válida no lugar
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "adulterado"
    assert any(m.startswith("arquivo_divergente:foto_") for m in corpo["visitas"][0]["motivos"])
    caminho.unlink()
    assert any(m.startswith("arquivo_ausente:") for m in _verificar(fluxo).json()["visitas"][0]["motivos"])


def test_assinatura_adulterada_em_disco_e_acusada(fluxo, db):
    _finalizar(fluxo)
    visita = db.get(Visita, fluxo.visita_id)
    caminho = file_service.ASSINATURA_DIRECTORY / visita.assinatura_url.rsplit("/", 1)[1]
    bruto = bytearray(caminho.read_bytes())
    bruto[20] ^= 0xFF
    caminho.write_bytes(bytes(bruto))
    motivos = _verificar(fluxo).json()["visitas"][0]["motivos"]
    assert "arquivo_adulterado:assinatura" in motivos


def test_selo_removido_do_banco_e_acusado_como_adulteracao_e_nao_como_legado(fluxo):
    _finalizar(fluxo)
    with engine.begin() as conn:  # alguém anula o selo para a visita parecer "legada"
        conn.execute(text("UPDATE visita SET selo_integridade=NULL, selo_versao=NULL WHERE id_visita=:i"), {"i": fluxo.visita_id})
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "adulterado" and corpo["visitas"][0]["motivos"] == ["selo_removido"]


def test_visita_legada_sem_selo_e_sem_registro_do_selo_no_log_e_sem_selo(fluxo, db):
    """Legado de verdade: nem a visita nem o log_acao têm selo (finalizada antes da v0.6) => não é adulteração."""
    _finalizar(fluxo)
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET selo_integridade=NULL, selo_versao=NULL WHERE id_visita=:i"), {"i": fluxo.visita_id})
    reg = db.query(LogAcao).filter(LogAcao.id_os == fluxo.os_id, LogAcao.acao == "ATENDIMENTO_FINALIZADO").one()
    reg.payload = {k: v for k, v in reg.payload.items() if k not in ("selo", "selo_versao")}
    db.commit()
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "sem_selo" and corpo["visitas"][0]["estado"] == "sem_selo"


def test_selo_trocado_por_outro_valor_diverge_do_registro_de_auditoria(fluxo):
    _finalizar(fluxo)
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET selo_integridade=:s WHERE id_visita=:i"), {"s": "a" * 64, "i": fluxo.visita_id})
    motivos = _verificar(fluxo).json()["visitas"][0]["motivos"]
    assert "selo_divergente" in motivos and "selo_diverge_da_auditoria" in motivos


def test_selo_vai_para_o_log_acao_na_finalizacao(fluxo, db):
    _finalizar(fluxo)
    reg = db.query(LogAcao).filter(LogAcao.id_os == fluxo.os_id, LogAcao.acao == "ATENDIMENTO_FINALIZADO").one()
    assert reg.payload["selo"] == db.get(Visita, fluxo.visita_id).selo_integridade and reg.payload["selo_versao"] == 1


# ---- Regressão do item 1 da revisão: o que ainda muda depois do atendimento NÃO pode quebrar o selo ------------------

def test_pedagio_comprovante_e_foto_da_ida_depois_do_atendimento_nao_quebram_o_selo(fluxo, db):
    _finalizar(fluxo)  # atendimento finalizado; a volta ainda não aconteceu
    assert _verificar(fluxo).json()["estado"] == "integro"

    nome, dados, mime = imagem(300, 200)
    r = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers,
                     data={"file_type": "comprovante_pedagio_urls", "sha256": _sha(dados)}, files={"file": (nome, dados, mime)})
    assert r.status_code == 200, r.text  # pedágio pago na volta
    r = fluxo.c.patch(fluxo.url(""), headers=fluxo.tecnico.headers, json={"valor_pedagio": 12.5, "valor_frete_devolucao": 7})
    assert r.status_code == 200, r.text
    assert fluxo.foto_deslocamento("ida", "fim").status_code == 200  # foto da ida reenviada
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "integro", corpo

    # o arquivo do comprovante continua sob conferência de hash (fora do selo, mas verificado)
    db.expire_all()
    from app.models.comprovante import Comprovante
    comp = db.query(Comprovante).filter(Comprovante.id_visita == fluxo.visita_id).one()
    (file_service.UPLOAD_DIRECTORY / comp.url.rsplit("/", 1)[1]).write_bytes(imagem(111, 222)[1])
    motivos = _verificar(fluxo).json()["visitas"][0]["motivos"]
    assert "arquivo_divergente:comprovante_pedagio" in motivos


def test_fluxo_completo_ate_a_os_finalizada_permanece_integro_em_cada_etapa(fluxo):
    _finalizar(fluxo)
    assert _verificar(fluxo).json()["estado"] == "integro"
    assert fluxo.volta_completa().status_code == 200  # OS Finalizada, custo congelado
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "integro", corpo


def test_desativar_o_tecnico_entre_o_atendimento_e_a_volta_nao_quebra_o_selo(fluxo):
    _finalizar(fluxo)
    r = fluxo.c.delete(f"/api/tecnicos/{fluxo.tecnico.id}", headers=fluxo.admin.headers)  # desatribui a OS (RN-08a)
    assert r.status_code == 204, r.text
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "integro", corpo


def test_visita_nao_finalizada_nao_tem_selo(fluxo):
    fluxo.ate_em_atendimento()
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "nao_finalizada"


def test_correcao_administrativa_de_materiais_resseala_e_audita(fluxo, db):
    _finalizar(fluxo)
    assert fluxo.volta_completa().status_code == 200  # OS Finalizada
    antes = db.get(Visita, fluxo.visita_id).selo_integridade
    sid = fluxo.servicos()[0]["id_servico"]
    r = fluxo.c.patch(fluxo.url(f"servicos/{sid}"), headers=fluxo.admin.headers,
                      json={"materiais_utilizados": [{"nome": "Capacitor", "quantidade": 2, "valor": 35.5}]})
    assert r.status_code == 200, r.text
    db.expire_all()
    novo = db.get(Visita, fluxo.visita_id).selo_integridade
    assert novo != antes
    assert _verificar(fluxo).json()["estado"] == "integro"  # a correção legítima não vira "adulterado"
    reselos = db.query(LogAcao).filter(LogAcao.id_os == fluxo.os_id, LogAcao.acao == "SELO_RESSELADO").all()
    assert len(reselos) == 1 and reselos[0].payload["selo_anterior"] == antes and reselos[0].payload["selo_novo"] == novo


# =====================================================================================================================
# Assinatura cifrada em disco + endpoint autenticado
# =====================================================================================================================

def test_assinatura_fica_cifrada_em_disco_e_nao_e_servida_por_static(fluxo, db, client):
    corpo = _finalizar(fluxo)
    nome = corpo["assinatura_url"].rsplit("/", 1)[1]
    assert nome.endswith(".enc")
    em_disco = (file_service.ASSINATURA_DIRECTORY / nome).read_bytes()
    assert not em_disco.startswith(b"\x89PNG")  # não é uma imagem legível
    assert client.get(f"/static/assinaturas/{nome}").status_code == 404


def test_endpoint_da_assinatura_devolve_a_imagem_original_so_para_quem_pode(fluxo, outro_tecnico):
    _finalizar(fluxo)
    original = base64.b64decode(assinatura_b64().split(",", 1)[1])
    url = f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}/assinatura"
    for quem in (fluxo.tecnico, fluxo.admin):
        r = fluxo.c.get(url, headers=quem.headers)
        assert r.status_code == 200 and r.content == original and r.headers["content-type"] == "image/png"
        assert "no-store" in r.headers["cache-control"]
    assert fluxo.c.get(url, headers=outro_tecnico.headers).status_code == 403
    assert fluxo.c.get(url).status_code == 401


def test_assinatura_antiga_em_claro_continua_sendo_servida_ate_a_conversao(fluxo, db):
    _finalizar(fluxo)
    legado = file_service.ASSINATURA_DIRECTORY / "legado.png"
    original = base64.b64decode(assinatura_b64().split(",", 1)[1])
    legado.write_bytes(original)
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET assinatura_url='/static/assinaturas/legado.png' WHERE id_visita=:i"),
                     {"i": fluxo.visita_id})
    r = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}/assinatura", headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.content == original


def test_leitura_de_arquivo_nao_aceita_path_traversal():
    assert file_service.ler_arquivo_por_url("/static/assinaturas/../../.env") is None
    assert file_service.ler_arquivo_por_url("/static/uploads/..%2f..%2f.env") is None
    assert file_service.ler_arquivo_por_url(None) is None


# =====================================================================================================================
# TLS
# =====================================================================================================================

def test_hsts_so_em_producao_e_em_todas_as_respostas(client, monkeypatch):
    assert "strict-transport-security" not in client.get("/").headers
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    r = client.get("/")
    assert r.headers["strict-transport-security"].startswith("max-age=31536000")
    assert "strict-transport-security" in client.get("/api/rota-inexistente").headers  # inclusive em 404


def test_conexao_com_o_banco_exige_tls_no_postgres(monkeypatch):
    from app.db import database
    assert database._connect_args("sqlite:///x.db") == {}  # testes
    monkeypatch.delenv("DB_SSLMODE", raising=False)
    assert database._connect_args("postgresql+psycopg2://u:p@h:5432/d") == {"sslmode": "require"}
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    monkeypatch.setenv("DB_SSLROOTCERT", "/certs/ca.crt")
    assert database._connect_args("postgresql://u:p@h/d") == {"sslmode": "verify-full", "sslrootcert": "/certs/ca.crt"}
    monkeypatch.setenv("DB_SSLMODE", "disable")
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    with pytest.raises(ValueError, match="TLS"):
        database._connect_args("postgresql://u:p@h/d")
    monkeypatch.setattr(config, "IS_PRODUCTION", False)
    monkeypatch.delenv("DB_SSLROOTCERT")
    assert database._connect_args("postgresql://u:p@h/d") == {"sslmode": "disable"}  # só dev local
    monkeypatch.setenv("DB_SSLMODE", "qualquer-coisa")
    with pytest.raises(ValueError):
        database._connect_args("postgresql://u:p@h/d")


# =====================================================================================================================
# Script de migração dos dados existentes (scripts/cifrar_dados_existentes.py)
# =====================================================================================================================

def _carregar_script():
    import importlib.util
    caminho = Path(__file__).resolve().parents[2] / "scripts" / "cifrar_dados_existentes.py"
    spec = importlib.util.spec_from_file_location("cifrar_dados_existentes", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def banco_legado(tmp_path):
    """SQLite temporário no formato 'pós-0011': colunas em texto, cnpj_idx ainda vazio e dados em CLARO."""
    from sqlalchemy import create_engine
    eng = create_engine(f"sqlite:///{(tmp_path / 'legado.db').as_posix()}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE tecnico (id_tecnico INTEGER PRIMARY KEY, cnpj TEXT, cpf TEXT, telefone TEXT, "
                       "banco TEXT, agencia TEXT, conta TEXT, pix TEXT, cnpj_idx TEXT)"))
        c.execute(text("CREATE TABLE visita (id_visita INTEGER PRIMARY KEY, documento_cliente TEXT, assinatura_url TEXT, "
                       "assinatura_sha256 TEXT, arquivos_sha256 TEXT, odometro_inicio_url TEXT, odometro_fim_url TEXT, "
                       "foto_inicio_ida_url TEXT, foto_fim_ida_url TEXT, foto_inicio_volta_url TEXT, foto_fim_volta_url TEXT)"))
        c.execute(text("CREATE TABLE sync_arquivo (client_file_id TEXT PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("CREATE TABLE servico_foto (id_foto INTEGER PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("CREATE TABLE comprovante (id_comprovante INTEGER PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("INSERT INTO tecnico VALUES (1, '11.222.333/0001-81', '529.982.247-25', '(27) 99999-0000', "
                       "'Banco X', '0001', '12345-6', 'pix@x.com', NULL)"))
        c.execute(text("INSERT INTO tecnico VALUES (2, '44.555.666/0001-00', '111.444.777-35', NULL, NULL, NULL, NULL, NULL, NULL)"))
        c.execute(text("INSERT INTO visita (id_visita, documento_cliente) VALUES (10, '52998224725')"))
        c.execute(text("INSERT INTO visita (id_visita) VALUES (11)"))
    yield eng
    eng.dispose()


def test_script_cifra_preenche_indice_cego_e_e_idempotente(banco_legado):
    mod = _carregar_script()
    feito = mod.cifrar_campos(banco_legado)
    assert feito["tecnico.cpf"] == 2 and feito["tecnico.cnpj_idx"] == 2 and feito["visita.documento_cliente"] == 1
    assert feito["tecnico.pix"] == 1  # NULL não conta
    assert all(v == 0 for v in mod.verificar_campos(banco_legado).values())
    with banco_legado.connect() as c:
        cpf, cnpj, idx = c.execute(text("SELECT cpf, cnpj, cnpj_idx FROM tecnico WHERE id_tecnico=1")).fetchone()
    assert cpf.startswith("enc1:") and crypto.decifrar(cpf, "tecnico.cpf") == "529.982.247-25"
    assert idx == Tecnico.indice_do_cnpj("11.222.333/0001-81") == Tecnico.indice_do_cnpj("11222333000181")
    assert mod.cifrar_campos(banco_legado) == {}  # segunda execução não faz nada (e não re-cifra)


def test_script_dry_run_nao_grava_e_decifrar_reverte(banco_legado):
    mod = _carregar_script()
    assert mod.cifrar_campos(banco_legado, dry_run=True)["tecnico.cpf"] == 2
    assert mod.verificar_campos(banco_legado)["tecnico.cpf"] == 2  # continua tudo em claro
    mod.cifrar_campos(banco_legado)
    revertido = mod.decifrar_campos(banco_legado)
    assert revertido["tecnico.cpf"] == 2
    with banco_legado.connect() as c:
        assert c.execute(text("SELECT cpf FROM tecnico WHERE id_tecnico=1")).scalar() == "529.982.247-25"
        assert c.execute(text("SELECT documento_cliente FROM visita WHERE id_visita=10")).scalar() == "52998224725"


def test_script_converte_assinatura_confere_e_preenche_hashes(banco_legado):
    mod = _carregar_script()
    original = base64.b64decode(assinatura_b64().split(",", 1)[1])
    file_service.ASSINATURA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    file_service.UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    (file_service.ASSINATURA_DIRECTORY / "antiga.png").write_bytes(original)
    foto = imagem(300, 200)[1]
    (file_service.UPLOAD_DIRECTORY / "foto.jpg").write_bytes(foto)
    with banco_legado.begin() as c:
        c.execute(text("UPDATE visita SET assinatura_url='/static/assinaturas/antiga.png', "
                       "foto_inicio_ida_url='/static/uploads/foto.jpg' WHERE id_visita=10"))
        c.execute(text("INSERT INTO sync_arquivo VALUES ('abc', '/static/assinaturas/antiga.png', NULL)"))
        c.execute(text("INSERT INTO servico_foto VALUES (1, '/static/uploads/foto.jpg', NULL)"))
        c.execute(text("INSERT INTO servico_foto VALUES (2, '/static/uploads/sumiu.jpg', NULL)"))
    r = mod.converter_assinaturas(banco_legado, dry_run=True)
    assert r["convertidas"] == [10] and (file_service.ASSINATURA_DIRECTORY / "antiga.png").exists()
    r = mod.converter_assinaturas(banco_legado)
    assert r["convertidas"] == [10] and r["apagadas"] == []
    with banco_legado.connect() as c:
        url, sha = c.execute(text("SELECT assinatura_url, assinatura_sha256 FROM visita WHERE id_visita=10")).fetchone()
        assert url.endswith(".enc") and sha == _sha(original)
        assert c.execute(text("SELECT url FROM sync_arquivo")).scalar() == url
    assert file_service.ler_arquivo_por_url(url) == original  # decifra para o original
    assert (file_service.ASSINATURA_DIRECTORY / "antiga.png").exists()  # original preservado sem --apagar-originais
    assert mod.converter_assinaturas(banco_legado)["ja_cifradas"] == [10]

    h = mod.preencher_hashes(banco_legado)
    assert h["servico_foto"] == 1 and h["sem_arquivo"] == 1 and h["visita.arquivos_sha256"] == 1
    with banco_legado.connect() as c:
        assert c.execute(text("SELECT sha256 FROM servico_foto WHERE id_foto=1")).scalar() == _sha(foto)
        assert c.execute(text("SELECT sha256 FROM servico_foto WHERE id_foto=2")).scalar() is None  # sem arquivo: não inventa
        assert json.loads(c.execute(text("SELECT arquivos_sha256 FROM visita WHERE id_visita=10")).scalar()) == {
            "foto_inicio_ida_url": _sha(foto)}


# =====================================================================================================================
# Revisão (item 3 e observações): padrões seguros
# =====================================================================================================================

def test_modo_legado_da_cifragem_e_desligado_por_padrao_e_recusado_em_producao():
    assert config.legacy_plaintext_enabled(None, production=False) is False
    assert config.legacy_plaintext_enabled("", production=False) is False
    assert config.legacy_plaintext_enabled("true", production=False) is True  # dev/teste, durante a migração
    assert config.legacy_plaintext_enabled("false", production=True) is False
    with pytest.raises(ValueError, match="ENV=production"):
        config.legacy_plaintext_enabled("true", production=True)


def test_sslmode_require_em_producao_avisa_que_o_certificado_nao_e_validado(monkeypatch, caplog):
    import logging
    from app.db import database
    monkeypatch.delenv("DB_SSLMODE", raising=False)
    monkeypatch.delenv("DB_SSLROOTCERT", raising=False)
    monkeypatch.setattr(config, "IS_PRODUCTION", True)
    with caplog.at_level(logging.WARNING, logger="app.db.database"):
        assert database._connect_args("postgresql://u:p@h/d") == {"sslmode": "require"}
    assert "NÃO É VALIDADO" in caplog.text
    caplog.clear()
    monkeypatch.setenv("DB_SSLMODE", "verify-full")
    with caplog.at_level(logging.WARNING, logger="app.db.database"):
        database._connect_args("postgresql://u:p@h/d")
    assert "NÃO É VALIDADO" not in caplog.text
