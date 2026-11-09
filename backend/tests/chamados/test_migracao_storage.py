"""Script de migração disco local -> bucket privado (scripts/migrar_arquivos_para_storage.py), em SQLite + bucket em memória."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core.crypto import cifrar_bytes
from app.services import file_service
from chamados.test_storage_privado import ArmazenamentoMemoria
from chamados.helpers import imagem


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _script():
    caminho = Path(__file__).resolve().parents[2] / "scripts" / "migrar_arquivos_para_storage.py"
    spec = importlib.util.spec_from_file_location("migrar_arquivos_para_storage", caminho)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def cenario(tmp_path):
    eng = create_engine(f"sqlite:///{(tmp_path / 'm.db').as_posix()}")
    cols_visita = ["odometro_inicio_url", "odometro_fim_url", "foto_inicio_ida_url", "foto_fim_ida_url",
                   "foto_inicio_volta_url", "foto_fim_volta_url"]
    with eng.begin() as c:
        c.execute(text("CREATE TABLE servico_foto (id_foto INTEGER PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("CREATE TABLE comprovante (id_comprovante INTEGER PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("CREATE TABLE sync_arquivo (client_file_id TEXT PRIMARY KEY, url TEXT, sha256 TEXT)"))
        c.execute(text("CREATE TABLE visita (id_visita INTEGER PRIMARY KEY, assinatura_url TEXT, assinatura_sha256 TEXT, "
                       "arquivos_sha256 TEXT, " + ", ".join(f"{col} TEXT" for col in cols_visita) + ")"))

    file_service.UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    file_service.ASSINATURA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    fotos = {n: imagem(300 + i, 200)[1] for i, n in enumerate(["a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg", "f.jpg"])}
    for n in ("a.jpg", "b.jpg", "c.jpg", "d.jpg", "e.jpg"):  # f.jpg fica só no banco (ausente)
        (file_service.UPLOAD_DIRECTORY / n).write_bytes(fotos[n])
    original_assin = imagem(200, 80, "PNG")[1]
    enc = cifrar_bytes(original_assin, file_service.CONTEXTO_ASSINATURA)
    (file_service.ASSINATURA_DIRECTORY / "s.enc").write_bytes(enc)
    (file_service.ASSINATURA_DIRECTORY / "claro.png").write_bytes(original_assin)

    with eng.begin() as c:
        ins = "INSERT INTO servico_foto (url, sha256) VALUES (:u, :h)"
        c.execute(text(ins), {"u": "/static/uploads/a.jpg", "h": _sha(fotos["a.jpg"])})   # ok, com hash
        c.execute(text(ins), {"u": "/static/uploads/b.jpg", "h": "0" * 64})                # hash do banco não bate
        c.execute(text(ins), {"u": "/static/uploads/d.jpg", "h": None})                    # sem hash; já estará no bucket
        c.execute(text(ins), {"u": "/static/uploads/e.jpg", "h": None})                    # bucket tem conteúdo diferente
        c.execute(text(ins), {"u": "/static/uploads/f.jpg", "h": None})                    # sem arquivo em lugar nenhum
        c.execute(text("INSERT INTO visita (id_visita, assinatura_url, assinatura_sha256) VALUES (1, :u, :h)"),
                  {"u": "/static/assinaturas/s.enc", "h": _sha(original_assin)})
        c.execute(text("INSERT INTO visita (id_visita, assinatura_url) VALUES (2, '/static/assinaturas/claro.png')"))

    bucket = ArmazenamentoMemoria()
    bucket.put("uploads", "d.jpg", fotos["d.jpg"], "image/jpeg")           # já migrado antes (idêntico)
    bucket.put("uploads", "e.jpg", b"conteudo diferente", "image/jpeg")    # conflito
    yield eng, bucket, fotos, enc
    eng.dispose()


def test_dry_run_nao_grava_nada(cenario):
    eng, bucket, _fotos, _enc = cenario
    antes = dict(bucket.itens)
    rel = _script().migrar(eng, bucket, dry_run=True)
    assert rel["migrado"] == ["uploads/a.jpg", "assinaturas/s.enc"] and bucket.itens == antes


def test_migra_confere_e_reporta_o_que_exige_decisao(cenario):
    eng, bucket, fotos, enc = cenario
    rel = _script().migrar(eng, bucket)
    assert rel["migrado"] == ["uploads/a.jpg", "assinaturas/s.enc"]
    assert rel["ja_no_bucket"] == ["uploads/d.jpg"]
    assert rel["conflito"] == ["uploads/e.jpg"]                 # nunca sobrescreve
    assert rel["divergente_do_banco"] == ["uploads/b.jpg"]      # hash do banco não bate: não sobe
    assert rel["orfao"] == ["uploads/c.jpg"]                    # ninguém referencia: não sobe por padrão
    assert rel["assinatura_em_claro"] == ["assinaturas/claro.png"]  # nunca sobe assinatura em claro
    assert rel["ausente"] == ["uploads/f.jpg"]
    # o que subiu é idêntico ao local, com o tipo certo; a assinatura sobe CIFRADA
    assert bucket.itens[("uploads", "a.jpg")] == (fotos["a.jpg"], "image/jpeg")
    assert bucket.itens[("assinaturas", "s.enc")] == (enc, "application/octet-stream")
    assert bucket.get("uploads", "e.jpg") == b"conteudo diferente"
    assert ("uploads", "b.jpg") not in bucket.itens and ("uploads", "c.jpg") not in bucket.itens
    assert ("assinaturas", "claro.png") not in bucket.itens


def test_e_idempotente(cenario):
    eng, bucket, _f, _e = cenario
    m = _script()
    m.migrar(eng, bucket)
    rel = m.migrar(eng, bucket)
    assert rel["migrado"] == [] and sorted(rel["ja_no_bucket"]) == ["assinaturas/s.enc", "uploads/a.jpg", "uploads/d.jpg"]


def test_orfaos_so_sobem_se_pedido(cenario):
    eng, bucket, _f, _e = cenario
    rel = _script().migrar(eng, bucket, incluir_orfaos=True)
    assert "uploads/c.jpg" in rel["migrado"] and ("uploads", "c.jpg") in bucket.itens


def test_apagar_locais_remove_so_o_que_esta_confirmado_no_bucket(cenario):
    eng, bucket, _f, _e = cenario
    rel = _script().migrar(eng, bucket, apagar_locais=True)
    assert sorted(rel["apagado_local"]) == ["assinaturas/s.enc", "uploads/a.jpg", "uploads/d.jpg"]
    up, ass = file_service.UPLOAD_DIRECTORY, file_service.ASSINATURA_DIRECTORY
    assert not (up / "a.jpg").exists() and not (up / "d.jpg").exists() and not (ass / "s.enc").exists()
    for ficou in (up / "b.jpg", up / "c.jpg", up / "e.jpg", ass / "claro.png"):  # conflito/divergente/órfão/claro: intactos
        assert ficou.exists(), ficou


def test_dry_run_com_apagar_locais_nao_apaga(cenario):
    eng, bucket, _f, _e = cenario
    _script().migrar(eng, bucket, dry_run=True, apagar_locais=True)
    assert (file_service.UPLOAD_DIRECTORY / "a.jpg").exists()


def test_falha_na_conferencia_pos_upload_interrompe_sem_apagar(cenario):
    eng, bucket, _f, _e = cenario

    class Corrompe(ArmazenamentoMemoria):
        def get(self, area, nome):
            item = self.itens.get((area, nome))
            return None if item is None else item[0][:-1] + b"\x00"  # devolve bytes diferentes do enviado

    ruim = Corrompe()
    with pytest.raises(RuntimeError, match="Conferencia falhou"):
        _script().migrar(eng, ruim, apagar_locais=True)
    assert (file_service.UPLOAD_DIRECTORY / "a.jpg").exists()
