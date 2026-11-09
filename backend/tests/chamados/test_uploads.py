"""
Uploads: T-08 (resolução só para conserto), T-24 (15 MB), MIME real (SEG-08), vínculo serviço/visita/OS e comprovantes.
"""
import os
from io import BytesIO

from PIL import Image

from app.models.comprovante import Comprovante
from app.services import file_service
from chamados.helpers import imagem


def _servico(fluxo) -> int:
    r = fluxo.servico()  # v0.5: o registro de serviço já existe (criado pelo servidor); o técnico o preenche
    assert r.status_code == 200, r.text
    return r.json()["id_servico"]


def _upload_foto(fluxo, servico_id, tipo, arquivo, headers=None):
    return fluxo.c.post(fluxo.url(f"servicos/{servico_id}/upload-foto"), headers=headers or fluxo.tecnico.headers,
                        data={"tipo": tipo}, files={"file": arquivo})


def _arquivos_gravados(pasta) -> list:
    return [p for p in pasta.rglob("*") if p.is_file()] if pasta.exists() else []


def test_t08_conserto_800x600_e_recusado_e_defeito_800x600_e_aceito(fluxo, tmp_path):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    antes = _arquivos_gravados(tmp_path / "uploads")
    r = _upload_foto(fluxo, sid, "conserto", imagem(800, 600))
    assert r.status_code == 400 and "Resolução insuficiente" in r.json()["detail"]
    assert _arquivos_gravados(tmp_path / "uploads") == antes  # nada persistido
    r = _upload_foto(fluxo, sid, "defeito", imagem(800, 600))
    assert r.status_code == 200, r.text
    assert r.json()["tipo"] == "defeito" and r.json()["id_foto"]


def test_conserto_960x1280_e_aceito_em_retrato_e_paisagem(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    assert _upload_foto(fluxo, sid, "conserto", imagem(960, 1280)).status_code == 200
    assert _upload_foto(fluxo, sid, "conserto", imagem(1280, 960)).status_code == 200
    assert _upload_foto(fluxo, sid, "conserto", imagem(959, 1280)).status_code == 400
    assert _upload_foto(fluxo, sid, "conserto", imagem(960, 1279)).status_code == 400


def test_defeito_odometro_e_deslocamento_nao_tem_resolucao_minima(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    assert _upload_foto(fluxo, sid, "defeito", imagem(10, 10)).status_code == 200
    assert fluxo.foto_deslocamento("ida", "fim", size=(10, 10)).status_code == 200
    r = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers,
                     data={"file_type": "odometro_inicio_url"}, files={"file": imagem(10, 10, "PNG")})
    assert r.status_code == 200 and r.json()["odometro_inicio_url"]


def test_get_fotos_lista_defeito_e_conserto(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    _upload_foto(fluxo, sid, "defeito", imagem(300, 200))
    _upload_foto(fluxo, sid, "conserto", imagem(1000, 1300))
    r = fluxo.c.get(fluxo.url(f"servicos/{sid}/fotos"), headers=fluxo.admin.headers)
    assert r.status_code == 200
    # v0.5: `ate_em_atendimento` já registrou 1 foto de defeito (pré-condição de iniciar); o teste enviou mais 1.
    assert len(r.json()["fotos_defeito"]) == 2 and len(r.json()["fotos_conserto"]) == 1
    assert {"id_foto", "id_servico", "tipo", "url"} <= set(r.json()["fotos_defeito"][0])


def test_tipo_de_foto_invalido_da_400(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    assert _upload_foto(fluxo, sid, "outro", imagem(300, 200)).status_code == 400


def test_t24_imagem_acima_do_limite_e_recusada_antes_de_persistir(fluxo, tmp_path, monkeypatch):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    antes = _arquivos_gravados(tmp_path / "uploads")
    monkeypatch.setattr(file_service, "MAX_IMAGE_BYTES", 2000)
    grande = ("grande.jpg", bytes([0xFF, 0xD8, 0xFF]) + os.urandom(5000), "image/jpeg")
    r = _upload_foto(fluxo, sid, "defeito", grande)
    assert r.status_code == 413
    assert "limite" in r.json()["detail"].lower()
    assert _arquivos_gravados(tmp_path / "uploads") == antes  # nenhum arquivo (nem parcial) foi persistido


def test_t24_imagem_de_ate_15mb_e_aceita(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    # ~3 MB de ruído em PNG (incompressível) deve passar: abaixo do limite de 15 MB
    ruido = Image.frombytes("RGB", (1000, 1000), os.urandom(1000 * 1000 * 3))
    buf = BytesIO()
    ruido.save(buf, format="PNG")
    assert len(buf.getvalue()) > 2 * 1024 * 1024
    r = _upload_foto(fluxo, sid, "defeito", ("ruido.png", buf.getvalue(), "image/png"))
    assert r.status_code == 200, r.text


def test_arquivo_que_nao_e_imagem_da_422_mesmo_com_content_type_de_imagem(fluxo, tmp_path):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    antes = _arquivos_gravados(tmp_path / "uploads")
    falso = ("foto.jpg", b"%PDF-1.4 isto e um pdf", "image/jpeg")
    r = _upload_foto(fluxo, sid, "defeito", falso)
    assert r.status_code == 422
    assert _arquivos_gravados(tmp_path / "uploads") == antes


def test_formato_nao_permitido_gif_e_recusado(fluxo):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    buf = BytesIO()
    Image.new("RGB", (50, 50)).save(buf, format="GIF")
    r = _upload_foto(fluxo, sid, "defeito", ("a.jpg", buf.getvalue(), "image/jpeg"))
    assert r.status_code == 422


def test_extensao_gravada_vem_do_formato_real_nao_do_nome(fluxo, tmp_path):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    nome, dados, _ = imagem(300, 200, "PNG")
    r = _upload_foto(fluxo, sid, "defeito", ("malicioso.php", dados, "application/x-php"))
    assert r.status_code == 200
    assert r.json()["url"].endswith(".png")


def test_servico_de_outra_visita_ou_os_nao_e_acessivel(fluxo, db, outro_tecnico, cliente_id):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    # outra OS do mesmo técnico: o serviço não pertence a esta visita
    from chamados.helpers import Fluxo
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, cliente_id)
    outra.criar_os()
    outra.criar_visita()
    r = outra.c.post(outra.url(f"servicos/{sid}/upload-foto"), headers=fluxo.tecnico.headers,
                     data={"tipo": "defeito"}, files={"file": imagem(300, 200)})
    assert r.status_code == 404
    r = outra.c.patch(outra.url(f"servicos/{sid}"), headers=fluxo.tecnico.headers,
                      json={"defeitos_principais": ["Refrigeração"]})
    assert r.status_code == 404
    r = outra.c.get(outra.url(f"servicos/{sid}/fotos"), headers=fluxo.admin.headers)
    assert r.status_code == 404


def test_upload_foto_de_servico_so_do_tecnico_atribuido(fluxo, outro_tecnico):
    fluxo.ate_em_atendimento()
    sid = _servico(fluxo)
    assert _upload_foto(fluxo, sid, "defeito", imagem(300, 200), headers=outro_tecnico.headers).status_code == 403
    # v0.5 (RN-49): o admin só envia foto de serviço como CORREÇÃO, com a OS Finalizada; fora disso, 409.
    r = _upload_foto(fluxo, sid, "defeito", imagem(300, 200), headers=fluxo.admin.headers)
    assert r.status_code == 409 and "Finalizado" in r.json()["detail"]


def test_upload_deslocamento_admin_e_atribuido_sim_outro_tecnico_nao(fluxo, outro_tecnico):
    fluxo.criar_os()
    fluxo.criar_visita()
    assert fluxo.foto_deslocamento("ida", "inicio", headers=outro_tecnico.headers).status_code == 403
    assert fluxo.foto_deslocamento("ida", "inicio", headers=fluxo.admin.headers).status_code == 200
    r = fluxo.foto_deslocamento("ida", "inicio")
    assert r.status_code == 200 and r.json()["foto_inicio_ida_url"]
    assert fluxo.c.post(fluxo.url("upload-deslocamento"), headers=fluxo.tecnico.headers,
                        data={"tipo": "meio", "momento": "inicio"},
                        files={"file": imagem(10, 10)}).status_code == 400


def test_comprovantes_criam_registros_na_tabela_comprovante(fluxo, db):
    fluxo.criar_os()
    fluxo.criar_visita()
    for ft, tipo in (("comprovante_pedagio_urls", "pedagio"), ("comprovante_pedagio_urls", "pedagio"),
                     ("comprovante_frete_urls", "frete")):
        r = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers, data={"file_type": ft},
                         files={"file": imagem(100, 100)})
        assert r.status_code == 200, r.text
    db.expire_all()
    registros = db.query(Comprovante).all()
    assert sorted(c.tipo for c in registros) == ["frete", "pedagio", "pedagio"]
    assert len(r.json()["comprovante_pedagio_urls"]) == 2 and len(r.json()["comprovante_frete_urls"]) == 1


def test_upload_file_tipo_invalido_da_400(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    r = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers, data={"file_type": "senha_url"},
                     files={"file": imagem(100, 100)})
    assert r.status_code == 400
