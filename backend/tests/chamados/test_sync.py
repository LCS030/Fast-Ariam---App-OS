"""
Sincronização offline (SDD 6.12): /api/sync/arquivos, /api/sync/eventos, /api/sync/minhas-os.

Cobre idempotência (T-18), horário do aparelho (T-19), conflito com ação do admin (T-20), rejeições FOTO_DEFEITO_AUSENTE /
CONSERTO_INCOMPLETO / ARQUIVO_AUSENTE e o fluxo completo offline até Finalizado. Roda no SQLite temporário.
"""
import base64
import uuid
from datetime import datetime, timedelta, timezone

from app.models.chamado import OrdemServico
from app.models.log_acao import LogAcao
from app.models.os_equipamento import OsEquipamento
from app.models.servico_foto import ServicoFoto
from app.models.sync_arquivo import SyncArquivo
from app.models.sync_evento import SyncEvento
from app.models.visita import Visita
from chamados.helpers import CPF_VALIDO, Fluxo, assinatura_b64, imagem

AGORA = lambda: datetime.now(timezone.utc)  # noqa: E731


def _id() -> str:
    return str(uuid.uuid4())


def _arquivo(fluxo, tipo, size=(300, 200), cfid=None, headers=None, os_id=None, visita_id=None, formato="JPEG"):
    cfid = cfid or _id()
    if tipo == "assinatura":
        arquivo = ("assinatura.png", base64.b64decode(assinatura_b64(com_prefixo=False)), "image/png")
    else:
        arquivo = imagem(*size, formato=formato)
    r = fluxo.c.post("/api/sync/arquivos", headers=headers or fluxo.tecnico.headers,
                     data={"client_file_id": cfid, "tipo_arquivo": tipo, "id_os": os_id or fluxo.os_id,
                           "id_visita": visita_id or fluxo.visita_id}, files={"file": arquivo})
    return cfid, r


def _ev(fluxo, tipo, payload, quando, cid=None, os_id=None, visita_id=None):
    return {"client_event_id": cid or _id(), "tipo": tipo, "id_os": os_id or fluxo.os_id,
            "id_visita": visita_id or fluxo.visita_id, "ocorrido_em": quando.isoformat(), "payload": payload}


def _enviar(fluxo, eventos, enviado_em=None, headers=None):
    corpo = {"dispositivo_id": "aparelho-1", "enviado_em": (enviado_em or AGORA()).isoformat(), "eventos": eventos}
    return fluxo.c.post("/api/sync/eventos", json=corpo, headers=headers or fluxo.tecnico.headers)


def _resultados(r):
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def _codigos(resultados):
    return [(x["resultado"], x["codigo"]) for x in resultados]


def _prep(fluxo, n_equip=1):
    fluxo.criar_os(n_equipamentos=n_equip)
    fluxo.criar_visita()
    return AGORA() - timedelta(hours=3)  # base: tudo "aconteceu" 3 h antes do envio (offline)


def _logs(db, acao):
    db.expire_all()
    return db.query(LogAcao).filter(LogAcao.acao == acao).all()


# =====================================================================================================================
# Fluxo completo, idempotência e horário do aparelho
# =====================================================================================================================
def _eventos_do_fluxo_completo(fluxo, base):
    f_ida, r = _arquivo(fluxo, "foto_deslocamento")
    assert r.status_code == 200 and r.json()["resultado"] == "aplicado", r.text
    f_def, _ = _arquivo(fluxo, "foto_defeito")
    f_con, r = _arquivo(fluxo, "foto_conserto", size=(960, 1280))
    assert r.status_code == 200, r.text
    f_ass, r = _arquivo(fluxo, "assinatura")
    assert r.status_code == 200, r.text
    f_volta, _ = _arquivo(fluxo, "foto_deslocamento")
    sid = fluxo.servicos()[0]["id_servico"]
    m = lambda x: base + timedelta(minutes=x)  # noqa: E731
    return [
        _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 1000, "foto_ref": f_ida}, m(0)),
        _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 1020}, m(10)),
        _ev(fluxo, "foto_servico", {"id_servico": sid, "tipo": "defeito", "foto_ref": f_def}, m(12)),
        _ev(fluxo, "atendimento_iniciado", {}, m(15)),
        _ev(fluxo, "servico_salvo", {"id_servico": sid, "defeitos_principais": ["Refrigeração"],
                                     "materiais_utilizados": [{"nome": "Compressor", "quantidade": 1, "valor": 850}]},
            m(20)),
        _ev(fluxo, "foto_servico", {"id_servico": sid, "tipo": "conserto", "foto_ref": f_con}, m(25)),
        _ev(fluxo, "conserto_salvo", {"id_servico": sid}, m(30)),
        _ev(fluxo, "atendimento_finalizado", {"nome_cliente": "Maria Gerente", "documento_cliente": CPF_VALIDO,
                                              "assinatura_ref": f_ass}, m(40)),
        _ev(fluxo, "deslocamento_volta_iniciado", {"km_inicio": 1020}, m(50)),
        _ev(fluxo, "deslocamento_volta_finalizado", {"km_fim": 1040, "foto_ref": f_volta}, m(60)),
    ]


def test_fluxo_completo_offline_vira_finalizado_com_o_horario_do_aparelho(fluxo, db):
    base = _prep(fluxo)
    eventos = _eventos_do_fluxo_completo(fluxo, base)
    res = _resultados(_enviar(fluxo, eventos))
    assert [x["resultado"] for x in res] == ["aplicado"] * 10, res
    os_ = fluxo.os()
    assert os_["status"] == "Finalizado"
    v = os_["visitas"][0]
    assert v["servico_finalizado"] is True and v["km_total"] == 40 and v["assinatura_url"]
    assert v["documento_cliente"] == "52998224725" and v["nome_cliente_assinatura"] == "Maria Gerente"
    # T-19: a visita grava o horário em que a ação OCORREU no aparelho (3 h antes do envio), não o do recebimento
    ida = datetime.fromisoformat(v["ida_inicio_em"].replace("Z", "+00:00"))
    ida = ida if ida.tzinfo else ida.replace(tzinfo=timezone.utc)  # SQLite devolve sem fuso (PostgreSQL devolve com)
    assert abs((ida - base).total_seconds()) < 1
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()["congelado"] is True
    db.expire_all()
    assert db.query(SyncEvento).filter(SyncEvento.resultado == "aplicado").count() == 10


def test_t18_reenviar_o_mesmo_lote_e_idempotente(fluxo, db):
    base = _prep(fluxo)
    eventos = _eventos_do_fluxo_completo(fluxo, base)
    assert [x["resultado"] for x in _resultados(_enviar(fluxo, eventos))] == ["aplicado"] * 10
    fotos = db.query(ServicoFoto).count()
    comprovantes_e_visitas = (db.query(Visita).count(), db.query(SyncEvento).count())
    segunda = _resultados(_enviar(fluxo, eventos))
    assert [x["resultado"] for x in segunda] == ["duplicado"] * 10
    db.expire_all()
    assert db.query(ServicoFoto).count() == fotos
    assert (db.query(Visita).count(), db.query(SyncEvento).count()) == comprovantes_e_visitas
    assert fluxo.os()["status"] == "Finalizado"


def test_eventos_sao_processados_por_ocorrido_em_e_a_resposta_vem_na_ordem_recebida(fluxo):
    base = _prep(fluxo)
    ida_i = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 10}, base)
    ida_f = _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 20}, base + timedelta(minutes=5))
    res = _resultados(_enviar(fluxo, [ida_f, ida_i]))  # fim ANTES do início no lote
    assert [x["client_event_id"] for x in res] == [ida_f["client_event_id"], ida_i["client_event_id"]]
    assert [x["resultado"] for x in res] == ["aplicado", "aplicado"]


def test_sy04_relogio_do_aparelho_atrasado_e_corrigido(fluxo, db):
    """Aparelho 3 h atrasado: enviado_em (relógio dele) está 3 h no passado; ocorrido_em é corrigido pelo desvio."""
    fluxo.criar_os()
    fluxo.criar_visita()
    relogio_aparelho = AGORA() - timedelta(hours=3)
    ev = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 5}, relogio_aparelho - timedelta(minutes=10))
    res = _resultados(_enviar(fluxo, [ev], enviado_em=relogio_aparelho))
    assert res[0]["resultado"] == "aplicado"
    db.expire_all()
    registro = db.get(SyncEvento, uuid.UUID(ev["client_event_id"]))
    esperado = AGORA() - timedelta(minutes=10)  # "10 min antes do envio", no relógio do servidor
    assert abs((registro.ocorrido_em.replace(tzinfo=timezone.utc) - esperado).total_seconds()) < 30
    assert "ocorrido_em_original" in registro.payload  # o valor original fica guardado


# =====================================================================================================================
# Pré-condições (TR-12 / TR-13) e arquivos
# =====================================================================================================================
def test_atendimento_iniciado_sem_foto_de_defeito_e_rejeitado_e_dependentes_ficam_bloqueados(fluxo, db):
    base = _prep(fluxo)
    sid = fluxo.servicos()[0]["id_servico"]
    m = lambda x: base + timedelta(minutes=x)  # noqa: E731
    eventos = [
        _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 1}, m(0)),
        _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 5}, m(5)),
        _ev(fluxo, "atendimento_iniciado", {}, m(10)),
        _ev(fluxo, "servico_salvo", {"id_servico": sid, "defeitos_principais": ["Refrigeração"]}, m(15)),
    ]
    res = _resultados(_enviar(fluxo, eventos))
    assert _codigos(res) == [("aplicado", None), ("aplicado", None), ("rejeitado", "FOTO_DEFEITO_AUSENTE"),
                             ("rejeitado", "DEPENDENCIA_REJEITADA")]
    assert fluxo.os()["status"] == "Agendado"
    # SY-08: corrige (envia a foto) e reenvia a ação com NOVO client_event_id
    f_def, _ = _arquivo(fluxo, "foto_defeito")
    novos = [_ev(fluxo, "foto_servico", {"id_servico": sid, "tipo": "defeito", "foto_ref": f_def}, m(20)),
             _ev(fluxo, "atendimento_iniciado", {}, m(21))]
    assert [x["resultado"] for x in _resultados(_enviar(fluxo, novos))] == ["aplicado", "aplicado"]
    assert fluxo.os()["status"] == "Em Atendimento"
    # a rejeição ficou gravada e rastreável (nunca descartada em silêncio)
    db.expire_all()
    assert db.get(SyncEvento, uuid.UUID(eventos[2]["client_event_id"])).codigo == "FOTO_DEFEITO_AUSENTE"


def test_atendimento_finalizado_sem_conserto_e_rejeitado_como_conserto_incompleto(fluxo):
    base = _prep(fluxo)
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    f_ass, _ = _arquivo(fluxo, "assinatura")
    ev = _ev(fluxo, "atendimento_finalizado", {"nome_cliente": "X", "documento_cliente": CPF_VALIDO,
                                              "assinatura_ref": f_ass}, AGORA() - timedelta(minutes=1))
    res = _resultados(_enviar(fluxo, [ev]))
    assert _codigos(res) == [("rejeitado", "CONSERTO_INCOMPLETO")]
    assert "conserto" in res[0]["detalhe"]


def test_arquivo_ausente_e_transitorio_nao_e_gravado_e_o_mesmo_evento_pode_ser_reenviado(fluxo, db):
    base = _prep(fluxo)
    ausente = _id()
    ev = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 7, "foto_ref": ausente}, base)
    seguinte = _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 9}, base + timedelta(minutes=5))
    res = _resultados(_enviar(fluxo, [ev, seguinte]))
    assert _codigos(res) == [("rejeitado", "ARQUIVO_AUSENTE"), ("rejeitado", "ARQUIVO_AUSENTE")]
    db.expire_all()
    assert db.query(SyncEvento).count() == 0  # transitório: nada gravado
    _arquivo(fluxo, "foto_deslocamento", cfid=ausente)
    res = _resultados(_enviar(fluxo, [ev, seguinte]))  # MESMOS client_event_id
    assert [x["resultado"] for x in res] == ["aplicado", "aplicado"]


def test_arquivos_validacao_idempotencia_e_permissao(fluxo, outro_tecnico):
    _prep(fluxo)
    cfid, r = _arquivo(fluxo, "foto_conserto", size=(800, 600))
    assert r.status_code == 400 and "Resolução insuficiente" in r.json()["detail"]
    cfid, r = _arquivo(fluxo, "foto_conserto", size=(1280, 960))  # paisagem vale
    assert r.status_code == 200
    url = r.json()["url"]
    _, r2 = _arquivo(fluxo, "foto_conserto", size=(1280, 960), cfid=cfid)
    assert r2.status_code == 200
    dup = r2.json()
    assert {k: dup[k] for k in ("client_file_id", "url", "resultado")} == {"client_file_id": cfid, "url": url,
                                                                           "resultado": "duplicado"}
    assert len(dup["sha256"]) == 64  # o servidor devolve o hash que gravou
    assert _arquivo(fluxo, "foto_defeito", size=(40, 30))[1].status_code == 200  # defeito sem resolução mínima
    assert _arquivo(fluxo, "outro_tipo")[1].status_code == 422
    assert _arquivo(fluxo, "foto_defeito", headers=outro_tecnico.headers)[1].status_code == 403
    assert _arquivo(fluxo, "foto_defeito", headers=fluxo.admin.headers)[1].status_code == 403
    gif = fluxo.c.post("/api/sync/arquivos", headers=fluxo.tecnico.headers,
                       data={"client_file_id": _id(), "tipo_arquivo": "foto_defeito", "id_os": fluxo.os_id,
                             "id_visita": fluxo.visita_id}, files={"file": ("a.jpg", b"%PDF-1.4 x", "image/jpeg")})
    assert gif.status_code == 422


def test_validacao_tipo_desconhecido_cpf_invalido_e_serie_no_payload(fluxo):
    base = _prep(fluxo)
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    sid = fluxo.servicos()[0]["id_servico"]
    f_ass, _ = _arquivo(fluxo, "assinatura")
    agora = AGORA() - timedelta(minutes=1)
    # um lote por evento: dentro do mesmo lote, a rejeição de um evento bloqueia os seguintes da visita (SY-01)
    for ev in (_ev(fluxo, "tipo_que_nao_existe", {}, agora),
               _ev(fluxo, "servico_salvo", {"id_servico": sid, "numero_serie_atendido": "HACK"}, agora),
               _ev(fluxo, "deslocamento_volta_iniciado", {}, agora)):  # km_inicio ausente
        assert _codigos(_resultados(_enviar(fluxo, [ev]))) == [("rejeitado", "VALIDACAO")], ev["tipo"]
    # CPF inválido na finalização (precisa do conserto completo para chegar na validação do CPF)
    fluxo.conserto_completo(estrito=True)
    ev = _ev(fluxo, "atendimento_finalizado", {"nome_cliente": "X", "documento_cliente": "111.111.111-11",
                                              "assinatura_ref": f_ass}, agora)
    assert _codigos(_resultados(_enviar(fluxo, [ev]))) == [("rejeitado", "VALIDACAO")]


# =====================================================================================================================
# Estado da OS (cancelada, reatribuída), permissões e conflitos (T-20)
# =====================================================================================================================
def test_os_cancelada_e_reatribuida_rejeitam_os_eventos(fluxo, outro_tecnico, db):
    base = _prep(fluxo)
    ev = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 1}, base)
    assert fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", json={"motivo": "teste"},
                        headers=fluxo.admin.headers).status_code == 200
    assert _codigos(_resultados(_enviar(fluxo, [ev]))) == [("rejeitado", "OS_CANCELADA")]
    # o arquivo de uma OS cancelada continua sendo aceito e guardado; só o evento é rejeitado (SY-06)
    assert _arquivo(fluxo, "foto_defeito")[1].status_code == 200
    # reatribuída: outra OS passa para outro técnico enquanto o aparelho estava offline
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.criar_os()
    outra.criar_visita()
    ev2 = _ev(outra, "deslocamento_ida_iniciado", {"km_inicio": 1}, base)
    r = outra.c.patch(f"/api/chamados/{outra.os_id}", json={"id_tecnico_atribuido": outro_tecnico.id},
                      headers=outra.admin.headers)
    assert r.status_code == 200, r.text
    assert _codigos(_resultados(_enviar(outra, [ev2]))) == [("rejeitado", "OS_REATRIBUIDA")]


def test_somente_o_tecnico_ativo_sincroniza(fluxo, db):
    base = _prep(fluxo)
    corpo = {"dispositivo_id": "d", "enviado_em": AGORA().isoformat(), "eventos": []}
    assert fluxo.c.post("/api/sync/eventos", json=corpo, headers=fluxo.admin.headers).status_code == 403
    assert fluxo.c.get("/api/sync/minhas-os", headers=fluxo.admin.headers).status_code == 403
    assert fluxo.c.post("/api/sync/eventos", json=corpo).status_code == 401
    # sem fuso: 422 para o lote inteiro
    ev = _ev(fluxo, "atendimento_iniciado", {}, base)
    ev["ocorrido_em"] = "2026-11-09T14:00:00"
    assert _enviar(fluxo, [ev]).status_code == 422
    # técnico desativado: 401 (SEG-01/SEG-15)
    assert fluxo.c.delete(f"/api/tecnicos/{fluxo.tecnico.id}", headers=fluxo.admin.headers).status_code == 204
    assert _enviar(fluxo, []).status_code == 401


def test_t20_equipamento_removido_pelo_admin_gera_conflito_e_a_os_vai_para_pendente(fluxo, db):
    mid = fluxo.criar_modelo()
    fluxo.criar_os(equipamentos=[{"id_equipamento_modelo": mid, "numero_serie": "C-1"},
                                 {"id_equipamento_modelo": mid, "numero_serie": "C-2"}])
    fluxo.criar_visita()
    servicos = fluxo.servicos()
    alvo = servicos[1]
    base = AGORA() - timedelta(hours=2)
    ev_ok = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 1}, base)
    ev_conflito = _ev(fluxo, "servico_salvo", {"id_servico": alvo["id_servico"],
                                               "defeitos_principais": ["Refrigeração"]}, base + timedelta(minutes=5))
    ev_depois = _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 5}, base + timedelta(minutes=6))
    # o administrador remove o equipamento C-2 enquanto o aparelho estava offline
    eq = fluxo.os()["equipamentos"][1]["id_os_equipamento"]
    assert fluxo.c.delete(f"/api/chamados/{fluxo.os_id}/equipamentos/{eq}", headers=fluxo.admin.headers).status_code == 204
    res = _resultados(_enviar(fluxo, [ev_ok, ev_conflito, ev_depois]))
    assert _codigos(res) == [("aplicado", None), ("rejeitado", "CONFLITO_ADMINISTRATIVO"),
                             ("rejeitado", "DEPENDENCIA_REJEITADA")]
    db.expire_all()
    os_ = db.get(OrdemServico, fluxo.os_id)
    assert os_.status.value == "Pendente" and os_.id_tecnico_atribuido is None  # SY-05 / SY-07
    (log,) = _logs(db, "CONFLITO_ADMINISTRATIVO")
    assert log.papel == "sistema" and log.payload["id_tecnico_anterior"] == fluxo.tecnico.id
    # o evento anterior e compatível permanece aplicado; o histórico da visita é preservado
    assert db.get(Visita, fluxo.visita_id).km_inicio_ida == 1
    assert db.get(SyncEvento, uuid.UUID(ev_conflito["client_event_id"])).resultado == "rejeitado"
    # depois do conflito o técnico não tem mais a OS: novos eventos dela são OS_REATRIBUIDA
    outro = _ev(fluxo, "deslocamento_ida_finalizado", {"km_fim": 9}, base + timedelta(minutes=9))
    assert _codigos(_resultados(_enviar(fluxo, [outro]))) == [("rejeitado", "OS_REATRIBUIDA")]


def test_t20_pausa_feita_pelo_admin_durante_o_offline_gera_conflito(fluxo, db):
    fluxo.ate_em_atendimento()
    sid = fluxo.servicos()[0]["id_servico"]
    assert fluxo.servico().status_code == 200
    # o administrador pausa a OS enquanto o técnico está offline
    assert fluxo.pausar(headers=fluxo.admin.headers).status_code == 200
    ev = _ev(fluxo, "conserto_salvo", {"id_servico": sid}, AGORA() - timedelta(minutes=1))
    res = _resultados(_enviar(fluxo, [ev]))
    assert _codigos(res) == [("rejeitado", "CONFLITO_ADMINISTRATIVO")]
    db.expire_all()
    os_ = db.get(OrdemServico, fluxo.os_id)
    assert os_.status.value == "Pendente" and os_.id_tecnico_atribuido is None
    assert len(_logs(db, "CONFLITO_ADMINISTRATIVO")) == 1


def test_pausa_do_proprio_tecnico_nao_e_conflito_e_sim_os_pausada(fluxo, db):
    fluxo.ate_em_atendimento()
    sid = fluxo.servicos()[0]["id_servico"]
    assert fluxo.servico().status_code == 200
    base = AGORA() - timedelta(minutes=10)
    res = _resultados(_enviar(fluxo, [
        _ev(fluxo, "pausa_registrada", {"motivo": "Peça pendente"}, base),
        _ev(fluxo, "conserto_salvo", {"id_servico": sid}, base + timedelta(minutes=1)),
    ]))
    assert _codigos(res) == [("aplicado", None), ("rejeitado", "OS_PAUSADA")]
    db.expire_all()
    assert db.get(OrdemServico, fluxo.os_id).status.value == "Pausado"  # sem Pendente: a pausa foi do próprio técnico


# =====================================================================================================================
# minhas-os (cache local)
# =====================================================================================================================
def test_minhas_os_traz_equipamentos_servicos_e_estado_e_nunca_a_os_de_outro_tecnico(fluxo, outro_tecnico, cliente_id):
    _prep(fluxo, n_equip=2)
    outra = Fluxo(fluxo.c, fluxo.admin, outro_tecnico, cliente_id)
    outra.criar_os()
    cancelada = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, cliente_id)
    cancelada.criar_os()
    cancelada.c.post(f"/api/chamados/{cancelada.os_id}/cancelar", json={"motivo": "x"}, headers=fluxo.admin.headers)
    r = fluxo.c.get("/api/sync/minhas-os", headers=fluxo.tecnico.headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["sincronizado_em"] and [i["chamado"]["id_os"] for i in corpo["os"]] == [fluxo.os_id]
    item = corpo["os"][0]
    assert len(item["chamado"]["equipamentos"]) == 2
    servicos = item["chamado"]["visitas"][0]["servicos_realizados"]
    assert len(servicos) == 2 and all(s["id_servico"] and s["id_os_equipamento"] for s in servicos)
    estado = item["estado_visita_vigente"]
    assert estado["visita_vigente"] is True and len(estado["equipamentos"]) == 2
    assert fluxo.c.get("/api/sync/minhas-os?desde=2026-01-01T00:00:00Z", headers=fluxo.tecnico.headers).status_code == 200
