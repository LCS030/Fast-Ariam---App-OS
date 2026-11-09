"""
Custos: PR-12 (chaves corretas), RN-31 (fórmula), RN-25 (sem ajudantes), T-22 (valores globais), CA-19 (snapshot).
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.models.configuracao_custo import ConfiguracaoCusto
from app.models.custo_os import CustoOS
from app.services.custo_service import CustoService, obter_valores_globais, valores_padrao_config
from chamados.helpers import criar_usuario

VALORES = {"primeira_hora_tecnico": 100.0, "hora_tecnico": 60.0, "tempo_deslocamento_tecnico": 20.0,
           "quilometragem": 2.0}


def _visita(**kw):
    base = {"id_visita": 7, "data_visita": date(2026, 11, 10), "km_total": 0, "valor_pedagio": 0.0,
            "valor_frete_devolucao": 0.0, "servicos_realizados": []}
    base.update(kw)
    return base


def _t(h, m=0):
    return datetime(2026, 11, 10, h, m, tzinfo=timezone.utc)


def test_pr12_usa_id_os_e_id_visita_corretos():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 42, "visitas": [_visita(id_visita=7)]})
    assert r.id_os == 42 and r.detalhes_por_visita[0].id_visita == 7


def test_rn31_ate_uma_hora_cobra_so_a_primeira_hora():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [
        _visita(atendimento_inicio_em=_t(9), atendimento_fim_em=_t(9, 30))]})
    assert r.custo_total_servico == 100.0
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [
        _visita(atendimento_inicio_em=_t(9), atendimento_fim_em=_t(10))]})
    assert r.custo_total_servico == 100.0  # exatamente 1h: ainda só a primeira hora


def test_rn31_acima_de_uma_hora_cobra_hora_adicional_proporcional():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [
        _visita(atendimento_inicio_em=_t(9), atendimento_fim_em=_t(10, 30))]})
    assert r.custo_total_servico == 130.0  # 100 + 0,5h * 60
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [
        _visita(atendimento_inicio_em=_t(9), atendimento_fim_em=_t(12))]})
    assert r.custo_total_servico == 220.0  # 100 + 2h * 60


def test_sem_atendimento_nao_cobra_servico():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [_visita()]})
    assert r.custo_total_servico == 0.0 and r.total_geral == 0.0


def test_formula_completa_materiais_km_pedagio_frete_deslocamento_servico():
    svc = CustoService(valores=VALORES)
    visita = _visita(
        km_total=50, valor_pedagio=9.8, valor_frete_devolucao=16.35,
        ida_inicio_em=_t(8), ida_fim_em=_t(8, 30), volta_inicio_em=_t(11), volta_fim_em=_t(11, 30),
        atendimento_inicio_em=_t(8, 40), atendimento_fim_em=_t(9, 40),
        servicos_realizados=[{"materiais_utilizados": [{"nome": "Filtro", "quantidade": 2, "valor": 85.0},
                                                        {"nome": "Gás", "quantidade": 1, "valor": 50.0}]}])
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [visita]})
    assert r.custo_total_materiais == 220.0
    assert r.custo_total_km == 100.0
    assert r.custo_total_pedagio == 9.8 and r.custo_total_frete == 16.35
    assert r.custo_total_deslocamento == 20.0  # (0,5h ida + 0,5h volta) * 20
    assert r.custo_total_servico == 100.0
    assert r.total_geral == round(220 + 100 + 9.8 + 16.35 + 20 + 100, 2)
    assert {m.nome: m.valor_total for m in r.detalhes_materiais_compilado} == {"Filtro": 170.0, "Gás": 50.0}


def test_fallback_para_horas_hhmm_legadas():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [
        _visita(hora_inicio_atendimento="09:00", hora_fim_atendimento="10:30")]})
    assert r.custo_total_servico == 130.0


def test_ajudantes_nao_entram_no_calculo():
    svc = CustoService(valores=VALORES)
    r = svc.calcular_custo_chamado({"id_os": 1, "visitas": [_visita(nome_ajudante="Carlos", telefone_ajudante="1")]})
    assert r.total_geral == 0.0
    assert "HORA_AJUDANTE" not in valores_padrao_config() and "hora_ajudante" not in svc.valores


def test_valores_globais_vem_de_configuracao_custo_com_fallback(db):
    padrao = valores_padrao_config()
    assert obter_valores_globais(db) == padrao  # sem linha: fallback config.py
    db.add(ConfiguracaoCusto(id_configuracao=1, primeira_hora_tecnico=Decimal("10.00"), hora_tecnico=Decimal("5.00"),
                             tempo_deslocamento_tecnico=Decimal("3.00"), quilometragem=Decimal("0.50")))
    db.commit()
    assert obter_valores_globais(db) == {"primeira_hora_tecnico": 10.0, "hora_tecnico": 5.0,
                                         "tempo_deslocamento_tecnico": 3.0, "quilometragem": 0.5}


def _fluxo_com_tempos(fluxo, km_ida=(1000, 1020), km_volta=(1020, 1040)):
    """Conduz uma visita completa com horários controlados via ocorrido_em (ida 30min, atend 90min, volta 30min)."""
    base = datetime.now(timezone.utc) - timedelta(hours=4)

    def em(minutos):
        return (base + timedelta(minutes=minutos)).isoformat()

    fluxo.criar_os()
    fluxo.criar_visita()
    assert fluxo.iniciar("ida", km_ida[0], ocorrido_em=em(0)).status_code == 200
    assert fluxo.foto_deslocamento("ida", "inicio").status_code == 200
    assert fluxo.finalizar("ida", km_ida[1], ocorrido_em=em(30)).status_code == 200
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(ocorrido_em=em(40)).status_code == 200
    fluxo.servico(materiais=[{"nome": "Compressor", "quantidade": 1, "valor": 850.0}])
    assert fluxo.finalizar_atendimento(ocorrido_em=em(130)).status_code == 200
    assert fluxo.iniciar("volta", km_volta[0], ocorrido_em=em(140)).status_code == 200
    assert fluxo.foto_deslocamento("volta", "fim").status_code == 200
    r = fluxo.finalizar("volta", km_volta[1], ocorrido_em=em(170))
    assert r.status_code == 200, r.text


def test_t22_snapshot_e_congelado_e_independe_de_mudancas_na_configuracao(fluxo, db):
    _fluxo_com_tempos(fluxo)
    primeiro = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()
    p = valores_padrao_config()
    assert primeiro["congelado"] is True
    assert primeiro["custo_total_km"] == round(40 * p["quilometragem"], 2)
    assert primeiro["custo_total_deslocamento"] == round(1.0 * p["tempo_deslocamento_tecnico"], 2)
    assert primeiro["custo_total_servico"] == round(p["primeira_hora_tecnico"] + 0.5 * p["hora_tecnico"], 2)
    assert primeiro["valores_utilizados"] == p

    # O administrador altera a configuração global DEPOIS da finalização: o histórico não pode mudar (CA-19 / RN-33).
    db.add(ConfiguracaoCusto(id_configuracao=1, primeira_hora_tecnico=Decimal("1.00"), hora_tecnico=Decimal("1.00"),
                             tempo_deslocamento_tecnico=Decimal("1.00"), quilometragem=Decimal("1.00")))
    db.commit()
    segundo = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()
    assert segundo["total_geral"] == primeiro["total_geral"]
    assert segundo["valores_utilizados"] == p

    snapshot = db.get(CustoOS, fluxo.os_id)
    assert float(snapshot.total) == primeiro["total_geral"]
    assert snapshot.valores_utilizados == p


def test_t22_os_nao_finalizada_usa_valores_globais_vigentes(fluxo, db):
    fluxo.ate_em_atendimento()
    db.add(ConfiguracaoCusto(id_configuracao=1, primeira_hora_tecnico=Decimal("1.00"), hora_tecnico=Decimal("1.00"),
                             tempo_deslocamento_tecnico=Decimal("1.00"), quilometragem=Decimal("7.00")))
    db.commit()
    r = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()
    assert r["congelado"] is False and r["valores_utilizados"]["quilometragem"] == 7.0


def test_t22_tecnicos_diferentes_usam_os_mesmos_valores_globais(fluxo, db, cliente_id):
    from chamados.helpers import Fluxo
    outro = criar_usuario(db, "tecnico")
    f1 = fluxo
    f2 = Fluxo(fluxo.c, fluxo.admin, outro, cliente_id)
    resultados = []
    for f in (f1, f2):
        f.criar_os()
        f.criar_visita()
        resultados.append(f.c.get(f"/api/chamados/{f.os_id}/custos", headers=f.admin.headers).json())
    assert resultados[0]["valores_utilizados"] == resultados[1]["valores_utilizados"]


def test_nao_existem_endpoints_de_configuracao_de_custo_por_tecnico(fluxo):
    for url in ("/api/tecnicos/me/configuracao-custo", f"/api/tecnicos/{fluxo.tecnico.id}/configuracao-custo"):
        for metodo in ("get", "put", "patch", "post"):
            r = getattr(fluxo.c, metodo)(url, headers=fluxo.tecnico.headers)
            assert r.status_code in (404, 405, 422), (metodo, url, r.status_code)
            assert r.status_code != 200
