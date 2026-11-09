"""
Serviços por equipamento (SDD 6.7) e robustez: validação de entrada, N+1 na listagem e atomicidade do cancelamento.
"""
import pytest
from sqlalchemy import event

from app.db.database import engine
from app.models.chamado import OrdemServico
from app.models.pausa import Pausa
from app.services import auditoria_service


def test_servico_crud_com_materiais_e_defeitos(fluxo):
    fluxo.ate_em_atendimento()
    # v0.5: o registro de serviço (um por equipamento da OS) já existe; o técnico o preenche por PATCH.
    r = fluxo.servico(materiais=[{"nome": "Filtro", "quantidade": 2, "valor": 85.5}],
                      sub_defeitos_refrigeracao=["Compressor"], sub_defeitos_compressor=["Queimado"])
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["id_os_equipamento"] and s["modelo"].startswith("Freezer") and s["numero_serie"].startswith("FZ-")
    assert s["materiais_utilizados"][0]["valor"] == 85.5 and s["sub_defeitos_compressor"] == ["Queimado"]
    sid = s["id_servico"]

    r = fluxo.c.patch(fluxo.url(f"servicos/{sid}"), headers=fluxo.tecnico.headers,
                      json={"sub_defeitos_compressor": ["Travado"],
                            "materiais_utilizados": [{"nome": "Gás", "quantidade": 1, "valor": 50}]})
    assert r.status_code == 200, r.text
    assert r.json()["sub_defeitos_compressor"] == ["Travado"]
    assert r.json()["sub_defeitos_refrigeracao"] == ["Compressor"]  # campo não enviado permanece
    assert [m["nome"] for m in r.json()["materiais_utilizados"]] == ["Gás"]

    lista = fluxo.c.get(fluxo.url("servicos"), headers=fluxo.admin.headers).json()
    assert len(lista) == 1 and lista[0]["id_servico"] == sid


def test_servico_com_rotulo_fora_da_lista_oficial_da_422_e_leitura_da_os_continua_ok(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.servico(sub_defeitos_compressor=["Inventado"])
    assert r.status_code == 422
    sid = fluxo.servicos()[0]["id_servico"]
    r = fluxo.c.patch(fluxo.url(f"servicos/{sid}"), headers=fluxo.tecnico.headers,
                      json={"materiais_utilizados": [{"nome": "x"}]})
    assert r.status_code == 422  # antes: KeyError -> 500
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers).status_code == 200


def test_os_detalhe_inclui_servicos_da_visita(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.servico(materiais=[{"nome": "Filtro", "quantidade": 1, "valor": 10}])
    visita = fluxo.os()["visitas"][0]
    servico = visita["servicos_realizados"][0]
    assert servico["modelo"].startswith("Freezer") and servico["numero_serie"].startswith("FZ-")
    assert servico["nome_equipamento"] is None and servico["is_legado"] is False  # série/nome legados não são usados


def test_listagem_nao_tem_n_mais_1(fluxo, db, cliente_id):
    """O número de SELECTs de GET /chamados/ não cresce com a quantidade de OS/visitas/serviços."""
    from chamados.helpers import Fluxo

    def montar(n):
        for _ in range(n):
            f = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, cliente_id)
            f.criar_os()
            f.criar_visita()
            f.ida_completa()
            f.fotos_defeito_todas()
            f.iniciar_atendimento()
            f.servico(materiais=[{"nome": "m", "quantidade": 1, "valor": 1}])

    contagem = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        contagem.append(statement)

    def selects_da_listagem():
        contagem.clear()
        event.listen(engine, "before_cursor_execute", contar)
        try:
            r = fluxo.c.get("/api/chamados/", headers=fluxo.admin.headers)
        finally:
            event.remove(engine, "before_cursor_execute", contar)
        assert r.status_code == 200
        return len(contagem), len(r.json())

    montar(2)
    q2, n2 = selects_da_listagem()
    montar(6)
    q8, n8 = selects_da_listagem()
    assert (n2, n8) == (2, 8)
    assert q8 == q2, f"N+1: {q2} consultas com 2 OS vs {q8} com 8 OS"


def test_cancelamento_e_atomico_se_a_auditoria_falhar(fluxo, db, monkeypatch):
    """Se qualquer passo do cancelamento falha, nada é gravado: OS não cancelada e pausa continua ativa."""
    fluxo.ate_em_atendimento()
    assert fluxo.pausar().status_code == 200

    def falha(*a, **k):
        raise RuntimeError("falha simulada na auditoria")

    monkeypatch.setattr(auditoria_service, "registrar_acao", falha)
    from app.main import app
    from fastapi.testclient import TestClient
    cliente_sem_propagar = TestClient(app, raise_server_exceptions=False)
    # reaproveita o override de get_db do fixture `client` (já ativo no app)
    r = cliente_sem_propagar.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers,
                                  json={"motivo": "teste"})
    assert r.status_code == 500
    db.expire_all()
    os_ = db.get(OrdemServico, fluxo.os_id)
    assert os_.is_cancelled is False and os_.motivo_cancelamento is None
    assert [p.is_ativa for p in db.query(Pausa).all()] == [True]


def test_finalizacao_e_atomica_se_o_snapshot_de_custo_falhar(fluxo, db, monkeypatch):
    fluxo.ate_em_atendimento()
    fluxo.finalizar_atendimento()
    from app.services import custo_service

    def falha(*a, **k):
        raise RuntimeError("falha simulada no snapshot")

    monkeypatch.setattr(custo_service, "congelar_custo", falha)
    from app.main import app
    from fastapi.testclient import TestClient
    sem_propagar = TestClient(app, raise_server_exceptions=False)
    assert fluxo.iniciar("volta", 1020).status_code == 200
    assert fluxo.foto_deslocamento("volta", "fim").status_code == 200
    r = sem_propagar.post(fluxo.url("finalizar-deslocamento"), headers=fluxo.tecnico.headers,
                          json={"tipo": "volta", "km_fim": 1040})
    assert r.status_code == 500
    db.expire_all()
    os_ = db.get(OrdemServico, fluxo.os_id)
    assert os_.status.value == "Em Atendimento" and os_.data_conclusao is None
    from app.models.visita import Visita
    visita = db.get(Visita, fluxo.visita_id)
    assert visita.servico_finalizado is False and visita.volta_fim_em is None and visita.km_total == 20
