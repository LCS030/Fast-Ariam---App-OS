"""
Permissões em TODAS as rotas de OS (T-03, SEG-09/SEG-11): técnico nunca vê/edita OS de outro técnico (403).
T-05/T-17 (técnico desativado) estão em test_desativacao_tecnico.py.
"""
from chamados.helpers import CPF_VALIDO, assinatura_b64, imagem


def _rotas(fluxo, servico_id):
    """(método, sufixo da URL, kwargs) de todas as rotas de OS/visita que um técnico de fora NÃO pode usar."""
    u = f"/api/chamados/{fluxo.os_id}"
    v = f"{u}/visitas/{fluxo.visita_id}"
    return [
        ("get", u, {}),
        ("patch", u, {"json": {"descricao_cliente": "x"}}),
        ("get", f"{u}/custos", {}),
        ("post", f"{u}/iniciar-atendimento", {}),
        ("post", f"{u}/visitas", {"json": {"data_visita": "2026-12-01"}}),
        ("patch", v, {"json": {"descricao_servico_executado": "x"}}),
        ("get", f"{v}/estado", {}),
        ("post", f"{v}/iniciar-deslocamento", {"json": {"tipo": "ida", "km_inicio": 1}}),
        ("post", f"{v}/finalizar-deslocamento", {"json": {"tipo": "ida", "km_fim": 2}}),
        ("post", f"{v}/upload-deslocamento", {"data": {"tipo": "ida", "momento": "inicio"},
                                              "files": {"file": imagem(10, 10)}}),
        ("post", f"{v}/upload_file", {"data": {"file_type": "odometro_inicio_url"}, "files": {"file": imagem(10, 10)}}),
        ("post", f"{v}/iniciar-atendimento", {}),
        ("post", f"{v}/pausar", {"json": {"motivo": "Peça pendente"}}),
        ("post", f"{v}/finalizar-atendimento", {"json": {"nome_cliente": "x", "documento_cliente": CPF_VALIDO,
                                                         "assinatura_base64": assinatura_b64()}}),
        ("get", f"{v}/servicos", {}),
        ("patch", f"{v}/servicos/{servico_id}", {"json": {"defeitos_principais": ["Refrigeração"]}}),
        ("post", f"{v}/servicos/{servico_id}/salvar-conserto", {"json": {}}),
        ("get", f"/api/chamados/{fluxo.os_id}/equipamentos", {}),
        ("post", f"{v}/servicos/{servico_id}/upload-foto", {"data": {"tipo": "defeito"},
                                                            "files": {"file": imagem(10, 10)}}),
        ("get", f"{v}/servicos/{servico_id}/fotos", {}),
    ]


def test_t03_tecnico_de_outra_os_recebe_403_em_todas_as_rotas(fluxo, outro_tecnico):
    fluxo.ate_em_atendimento()
    servico_id = fluxo.servico().json()["id_servico"]
    for metodo, url, kw in _rotas(fluxo, servico_id):
        r = getattr(fluxo.c, metodo)(url, headers=outro_tecnico.headers, **kw)
        assert r.status_code == 403, f"{metodo.upper()} {url} -> {r.status_code} {r.text}"
    # nada foi alterado pelas tentativas
    os_ = fluxo.os()
    assert os_["status"] == "Em Atendimento" and len(os_["visitas"]) == 1


def test_rotas_exclusivas_do_admin_recusam_tecnico(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    u = f"/api/chamados/{fluxo.os_id}"
    assert fluxo.c.post("/api/chamados/", headers=fluxo.tecnico.headers,
                        json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x"}).status_code == 403
    assert fluxo.c.post(f"{u}/cancelar", headers=fluxo.tecnico.headers, json={"motivo": "x"}).status_code == 403
    assert fluxo.c.post(f"{u}/reagendar", headers=fluxo.tecnico.headers,
                        json={"data_visita": "2026-12-01"}).status_code == 403


def test_rotas_exclusivas_do_tecnico_recusam_admin(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    for sufixo, body in (("iniciar-deslocamento", {"tipo": "ida", "km_inicio": 1}),
                         ("finalizar-deslocamento", {"tipo": "ida", "km_fim": 2}),
                         ("iniciar-atendimento", {})):
        r = fluxo.post(sufixo, body, headers=fluxo.admin.headers)
        assert r.status_code == 403, sufixo


def test_admin_le_qualquer_os_e_visita(fluxo):
    fluxo.ate_em_atendimento()
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers).status_code == 200
    # v0.5 (TR-13): sem conserto salvo + foto de conserto, nem o estado liberaria a finalização
    assert fluxo.estado(headers=fluxo.admin.headers)["pode_finalizar_atendimento"] is False
    fluxo.conserto_completo(estrito=True)
    assert fluxo.estado(headers=fluxo.admin.headers)["pode_finalizar_atendimento"] is True
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).status_code == 200


def test_visita_de_outra_os_retorna_404(fluxo, cliente_id):
    from chamados.helpers import Fluxo
    fluxo.criar_os()
    fluxo.criar_visita()
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, cliente_id)
    outra.criar_os()
    r = fluxo.c.get(f"/api/chamados/{outra.os_id}/visitas/{fluxo.visita_id}/estado", headers=fluxo.admin.headers)
    assert r.status_code == 404


def test_os_inexistente_e_cancelada_retornam_404(fluxo):
    assert fluxo.c.get("/api/chamados/99999", headers=fluxo.admin.headers).status_code == 404
    fluxo.criar_os()
    fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers, json={"motivo": "x"})
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers).status_code == 404
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).status_code == 404


def test_sem_token_retorna_401(fluxo):
    assert fluxo.c.get("/api/chamados/").status_code == 401
