"""
Criação, atribuição, PATCH, cancelamento e reagendamento: T-04, T-06, T-10, T-13, T-14, T-26 (+ TR-01, TR-08, RN-10).
"""
import pytest
from fastapi import HTTPException

from app.models.log_acao import LogAcao
from app.models.pausa import Pausa
from app.schemas.base_schemas import StatusChamado
from app.services.chamado_service import AcaoOS, validar_transicao
from chamados.helpers import criar_usuario, db_os, futuro

S = StatusChamado


# ---------------------------------------------------------------------------------------------------------------------
# Validador central (PR-13 / TR-01)
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("origem,acao,destino", [
    (None, AcaoOS.CRIAR_SEM_TECNICO, S.PENDENTE),
    (None, AcaoOS.CRIAR_COM_TECNICO, S.AGENDADO),
    (S.PENDENTE, AcaoOS.ATRIBUIR_TECNICO, S.AGENDADO),
    (S.AGENDADO, AcaoOS.INICIAR_ATENDIMENTO, S.EM_ATENDIMENTO),
    (S.EM_ATENDIMENTO, AcaoOS.PAUSAR, S.PAUSADO),
    (S.EM_ATENDIMENTO, AcaoOS.FINALIZAR_VOLTA_SEM_PAUSA, S.FINALIZADO),
    (S.PAUSADO, AcaoOS.FINALIZAR_VOLTA_COM_PAUSA, S.AGUARDANDO_REAGENDAMENTO),
    (S.AGUARDANDO_REAGENDAMENTO, AcaoOS.REAGENDAR_APOS_PAUSA, S.AGENDADO),
    (S.AGENDADO, AcaoOS.REAGENDAR_ANTES_DA_IDA, S.AGENDADO),
])
def test_transicoes_permitidas(origem, acao, destino):
    assert validar_transicao(origem, acao) == destino


@pytest.mark.parametrize("origem,acao", [
    (S.PENDENTE, AcaoOS.INICIAR_ATENDIMENTO),          # Pendente nunca inicia atendimento
    (S.FINALIZADO, AcaoOS.INICIAR_ATENDIMENTO),
    (S.PAUSADO, AcaoOS.INICIAR_ATENDIMENTO),
    (S.AGENDADO, AcaoOS.PAUSAR),
    (S.PAUSADO, AcaoOS.PAUSAR),
    (S.PAUSADO, AcaoOS.FINALIZAR_VOLTA_SEM_PAUSA),
    (S.EM_ATENDIMENTO, AcaoOS.FINALIZAR_VOLTA_COM_PAUSA),
    (S.PAUSADO, AcaoOS.REAGENDAR_APOS_PAUSA),           # TR-04: Pausado nao reagenda
    (S.EM_ATENDIMENTO, AcaoOS.REAGENDAR_APOS_PAUSA),
    (S.FINALIZADO, AcaoOS.CANCELAR),
    (S.AGENDADO, AcaoOS.ATRIBUIR_TECNICO),
])
def test_transicoes_invalidas_retornam_409_com_explicacao(origem, acao):
    with pytest.raises(HTTPException) as exc:
        validar_transicao(origem, acao)
    assert exc.value.status_code == 409
    assert origem.value in exc.value.detail and acao.value in exc.value.detail


# ---------------------------------------------------------------------------------------------------------------------
# T-26 / RN-10 / T-06
# ---------------------------------------------------------------------------------------------------------------------
def test_t26_os_sem_tecnico_nasce_pendente_e_nunca_aberto(fluxo, db):
    os_ = fluxo.criar_os(com_tecnico=False)
    assert os_["status"] == "Pendente"
    assert os_["id_tecnico_atribuido"] is None
    assert db_os(db, os_["id_os"]).status != S.ABERTO


def test_os_com_tecnico_ativo_nasce_agendada(fluxo):
    os_ = fluxo.criar_os(com_tecnico=True, data_agendamento="2026-11-10")
    assert os_["status"] == "Agendado"
    assert os_["id_tecnico_atribuido"] == fluxo.tecnico.id


def test_criar_os_ignora_status_enviado_pelo_cliente(fluxo):
    os_ = fluxo.criar_os(com_tecnico=False, status="Finalizado")
    assert os_["status"] == "Pendente"


def test_criar_os_com_tecnico_inativo_ou_inexistente_falha(fluxo, db):
    inativo = criar_usuario(db, "tecnico", ativo=False)
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x",
                           "equipamentos": fluxo.novos_equipamentos(), "id_tecnico_atribuido": inativo.id})
    assert r.status_code == 404
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x",
                           "equipamentos": fluxo.novos_equipamentos(), "id_tecnico_atribuido": 99999})
    assert r.status_code == 404


def test_criar_os_com_cliente_inativo_falha(fluxo, db):
    from chamados.helpers import criar_cliente
    inativo = criar_cliente(db, ativo=False)
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": inativo, "descricao_cliente": "x",
                           "equipamentos": fluxo.novos_equipamentos()})
    assert r.status_code == 404


def test_tecnico_nao_cria_os(fluxo):
    r = fluxo.c.post("/api/chamados/", headers=fluxo.tecnico.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x"})
    assert r.status_code == 403


def test_t06_atribuir_tecnico_pendente_vira_agendado(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": fluxo.tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Agendado"
    assert r.json()["id_tecnico_atribuido"] == fluxo.tecnico.id


def test_atribuir_tecnico_inativo_e_rejeitado(fluxo, db):
    inativo = criar_usuario(db, "tecnico", ativo=False)
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": inativo.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 404
    assert fluxo.os()["status"] == "Pendente"


def test_atribuir_admin_como_tecnico_e_rejeitado(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": fluxo.admin.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 400


def test_patch_com_status_agendado_valido_na_atribuicao_e_aceito(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}",
                      json={"id_tecnico_atribuido": fluxo.tecnico.id, "status": "Agendado"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["status"] == "Agendado"


def test_patch_status_legado_em_maiusculas_da_422(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}",
                      json={"id_tecnico_atribuido": fluxo.tecnico.id, "status": "AGENDADO"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 422


def test_t04_tecnico_nao_finaliza_por_patch(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": "Finalizado"}, headers=fluxo.tecnico.headers)
    assert r.status_code == 403
    assert fluxo.os()["status"] == "Em Atendimento"


def test_t04_admin_tambem_nao_finaliza_por_patch(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": "Finalizado"}, headers=fluxo.admin.headers)
    assert r.status_code == 403
    assert fluxo.os()["status"] == "Em Atendimento"


def test_tecnico_nao_escolhe_status_por_patch(fluxo):
    fluxo.criar_os()
    for status in ("Em Atendimento", "Agendado", "Pausado"):
        r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": status}, headers=fluxo.tecnico.headers)
        assert r.status_code == 403


def test_admin_nao_altera_status_arbitrario_por_patch(fluxo):
    fluxo.criar_os()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": "Em Atendimento"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 409
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": "Pausado"}, headers=fluxo.admin.headers)
    assert r.status_code == 409
    assert fluxo.os()["status"] == "Agendado"


def test_patch_nao_cancela_nem_conclui(fluxo):
    fluxo.criar_os()
    assert fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"is_cancelled": True},
                         headers=fluxo.admin.headers).status_code == 400
    assert fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"data_conclusao": "2026-11-01"},
                         headers=fluxo.admin.headers).status_code == 400


def test_nao_desatribui_os_agendada_por_patch_rn08a(fluxo):
    fluxo.criar_os()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": None},
                      headers=fluxo.admin.headers)
    assert r.status_code == 409
    assert fluxo.os()["id_tecnico_atribuido"] == fluxo.tecnico.id


def test_reatribuir_os_em_atendimento_e_bloqueado(fluxo, outro_tecnico):
    fluxo.ate_em_atendimento()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": outro_tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 409


def test_reatribuir_os_agendada_funciona_e_mantem_status(fluxo, outro_tecnico):
    fluxo.criar_os()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": outro_tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200
    assert r.json()["status"] == "Agendado" and r.json()["id_tecnico_atribuido"] == outro_tecnico.id


def test_patch_sem_dados_retorna_400(fluxo):
    fluxo.criar_os()
    assert fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={}, headers=fluxo.admin.headers).status_code == 400


def test_nao_existe_delete_de_chamado(fluxo):
    fluxo.criar_os()
    r = fluxo.c.delete(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers)
    assert r.status_code == 405


# ---------------------------------------------------------------------------------------------------------------------
# T-10: listagem com visita incompleta
# ---------------------------------------------------------------------------------------------------------------------
def test_t10_listar_os_com_visita_incompleta_retorna_200(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()  # sem horários, sem km, sem serviços
    r = fluxo.c.get("/api/chamados/", headers=fluxo.admin.headers)
    assert r.status_code == 200
    visita = r.json()[0]["visitas"][0]
    assert visita["km_total"] == 0
    assert visita["ida_inicio_em"] is None and visita["hora_inicio_ida"] is None
    assert r.json()[0]["cliente_nome"].startswith("Cliente")
    # o técnico também lista a sua OS
    assert fluxo.c.get("/api/chamados/", headers=fluxo.tecnico.headers).status_code == 200


def test_lista_do_tecnico_so_tem_as_suas_e_nao_as_canceladas(fluxo, outro_tecnico):
    fluxo.criar_os()
    primeira = fluxo.os_id
    fluxo.criar_os()
    segunda = fluxo.os_id
    c = fluxo.c
    c.post("/api/chamados/", headers=fluxo.admin.headers,
           json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "dele", "id_tecnico_atribuido": outro_tecnico.id})
    c.post(f"/api/chamados/{segunda}/cancelar", headers=fluxo.admin.headers, json={"motivo": "duplicada"})
    ids = [o["id_os"] for o in c.get("/api/chamados/", headers=fluxo.tecnico.headers).json()]
    assert ids == [primeira]
    ids_admin = {o["id_os"] for o in c.get("/api/chamados/", headers=fluxo.admin.headers).json()}
    assert primeira in ids_admin and segunda in ids_admin
    canceladas = c.get("/api/chamados/?is_cancelled=true", headers=fluxo.admin.headers).json()
    assert [o["id_os"] for o in canceladas] == [segunda]


# ---------------------------------------------------------------------------------------------------------------------
# T-14: cancelamento
# ---------------------------------------------------------------------------------------------------------------------
def test_t14_cancelar_exige_motivo_e_grava_campos(fluxo, db):
    fluxo.ate_em_atendimento()
    url = f"/api/chamados/{fluxo.os_id}/cancelar"
    assert fluxo.c.post(url, headers=fluxo.admin.headers, json={}).status_code == 422
    assert fluxo.c.post(url, headers=fluxo.admin.headers, json={"motivo": "   "}).status_code == 422
    assert fluxo.c.post(url, headers=fluxo.admin.headers, json={"motivo": "x" * 501}).status_code == 422
    r = fluxo.c.post(url, headers=fluxo.admin.headers, json={"motivo": "Cliente desistiu"})
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["is_cancelled"] is True
    assert corpo["motivo_cancelamento"] == "Cliente desistiu"
    assert corpo["cancelado_em"] is not None
    assert corpo["cancelado_por"] == fluxo.admin.id
    # o técnico deixa de ver a OS; as visitas ficam preservadas
    assert fluxo.c.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.tecnico.headers).status_code == 404
    db.expire_all()
    assert len(db_os(db, fluxo.os_id).visitas) == 1


def test_cancelar_duas_vezes_e_409(fluxo):
    fluxo.criar_os()
    url = f"/api/chamados/{fluxo.os_id}/cancelar"
    assert fluxo.c.post(url, headers=fluxo.admin.headers, json={"motivo": "a"}).status_code == 200
    r = fluxo.c.post(url, headers=fluxo.admin.headers, json={"motivo": "b"})
    assert r.status_code == 409


def test_t14_cancelar_os_finalizada_e_409(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.finalizar_atendimento()
    assert fluxo.volta_completa().status_code == 200
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers, json={"motivo": "x"})
    assert r.status_code == 409
    assert fluxo.os()["status"] == "Finalizado"


def test_cancelar_e_so_para_admin(fluxo):
    fluxo.criar_os()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.tecnico.headers, json={"motivo": "x"})
    assert r.status_code == 403


def test_cancelar_os_pausada_encerra_pausas_na_mesma_transacao(fluxo, db):
    fluxo.ate_em_atendimento()
    assert fluxo.pausar("Peça pendente").status_code == 200
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers, json={"motivo": "sem peça"})
    assert r.status_code == 200
    db.expire_all()
    pausas = db.query(Pausa).all()
    assert len(pausas) == 1 and pausas[0].is_ativa is False and pausas[0].encerrada_em is not None


def test_cancelar_os_inexistente_e_404(fluxo):
    r = fluxo.c.post("/api/chamados/99999/cancelar", headers=fluxo.admin.headers, json={"motivo": "x"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------------------------------------------------
# T-13 / T-02: reagendamento
# ---------------------------------------------------------------------------------------------------------------------
def _reagendar(fluxo, data=None):
    return fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                        json={"data_visita": data or futuro(10)})


def test_t13_reagendar_pendente_e_409(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = _reagendar(fluxo)
    assert r.status_code == 409 and "Pendente" in r.json()["detail"]


def test_t13_reagendar_agendado_com_ida_nao_iniciada_altera_visita_existente(fluxo):
    fluxo.criar_os()
    visita = fluxo.criar_visita(futuro(3))
    r = _reagendar(fluxo, futuro(8))
    assert r.status_code == 200, r.text
    assert r.json()["id_visita"] == visita["id_visita"] and r.json()["data_visita"] == futuro(8)
    os_ = fluxo.os()
    assert len(os_["visitas"]) == 1  # não criou visita vazia
    assert os_["data_agendamento"] == futuro(8) and os_["status"] == "Agendado"


def test_t13_reagendar_agendado_com_ida_iniciada_e_409(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.iniciar("ida", 10)
    assert _reagendar(fluxo).status_code == 409


def test_t13_reagendar_em_atendimento_e_409(fluxo):
    fluxo.ate_em_atendimento()
    r = _reagendar(fluxo)
    assert r.status_code == 409 and "Em Atendimento" in r.json()["detail"]


def test_t13_reagendar_pausado_e_409(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.pausar("Cliente ausente")
    r = _reagendar(fluxo)
    assert r.status_code == 409 and "Pausado" in r.json()["detail"]


def test_t13_reagendar_finalizado_e_409(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.finalizar_atendimento()
    fluxo.volta_completa()
    assert _reagendar(fluxo).status_code == 409


def test_t13_reagendar_cancelada_e_404(fluxo):
    fluxo.criar_os()
    fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers, json={"motivo": "x"})
    assert _reagendar(fluxo).status_code == 404


def test_reagendar_e_so_para_admin(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.tecnico.headers,
                     json={"data_visita": futuro(8)})
    assert r.status_code == 403


def test_t02_pausa_volta_e_reagendamento(fluxo, db):
    """T-02: pausar -> finalizar volta => Aguardando Reagendamento (pausa ativa); reagendar => Agendado + nova visita."""
    fluxo.ate_em_atendimento()
    assert fluxo.pausar("Peça pendente").status_code == 200
    assert fluxo.os()["status"] == "Pausado"
    # finalizar-atendimento bloqueado enquanto pausada
    assert fluxo.finalizar_atendimento().status_code == 400

    assert fluxo.iniciar("volta", 1020).status_code == 200
    assert fluxo.foto_deslocamento("volta", "fim").status_code == 200
    r = fluxo.finalizar("volta", 1040)
    assert r.status_code == 200, r.text
    assert r.json()["servico_finalizado"] is True
    os_ = fluxo.os()
    assert os_["status"] == "Aguardando Reagendamento" and os_["data_conclusao"] is None
    db.expire_all()
    assert [p.is_ativa for p in db.query(Pausa).all()] == [True]  # segue ativa até reagendar
    from app.models.custo_os import CustoOS
    assert db.query(CustoOS).count() == 0  # custo só é congelado na finalização

    r = _reagendar(fluxo, futuro(20))
    assert r.status_code == 201, r.text
    assert r.json()["id_visita"] != fluxo.visita_id and r.json()["servico_finalizado"] is False
    os_ = fluxo.os()
    assert os_["status"] == "Agendado" and os_["data_agendamento"] == futuro(20) and len(os_["visitas"]) == 2
    db.expire_all()
    pausa = db.query(Pausa).one()
    assert pausa.is_ativa is False and pausa.encerrada_em is not None


def test_t16_assinatura_por_visita_apos_reagendamento(fluxo):
    """T-16 / PR-35: cada visita tem a propria assinatura; a 2a nao sobrescreve a 1a."""
    fluxo.ate_em_atendimento()
    visita1 = fluxo.visita_id
    fluxo.pausar("Cliente ausente")
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")
    assert fluxo.finalizar("volta", 1040).status_code == 200
    r = _reagendar(fluxo, futuro(30))
    visita2 = r.json()["id_visita"]
    fluxo.visita_id = visita2
    fluxo.ida_completa(2000, 2020)
    assert fluxo.iniciar_atendimento().status_code == 200
    assert fluxo.finalizar_atendimento(nome="Segundo Cliente").status_code == 200

    visitas = {v["id_visita"]: v for v in fluxo.os()["visitas"]}
    assert visitas[visita2]["nome_cliente_assinatura"] == "Segundo Cliente"
    assert visitas[visita2]["assinatura_url"]
    # a visita 1 foi pausada antes de assinar: continua sem assinatura e não herdou a da visita 2
    assert visitas[visita1]["assinatura_url"] is None
    assert visitas[visita1]["nome_cliente_assinatura"] is None


# ---------------------------------------------------------------------------------------------------------------------
# Auditoria (PR-20)
# ---------------------------------------------------------------------------------------------------------------------
def test_acoes_relevantes_geram_log_acao(fluxo, db):
    fluxo.criar_os(com_tecnico=False)
    fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": fluxo.tecnico.id},
                  headers=fluxo.admin.headers)
    fluxo.criar_visita()
    fluxo.ida_completa()
    fluxo.iniciar_atendimento()
    fluxo.pausar("Peça pendente")
    fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", headers=fluxo.admin.headers, json={"motivo": "teste"})
    db.expire_all()
    acoes = [a.acao for a in db.query(LogAcao).filter(LogAcao.id_os == fluxo.os_id).order_by(LogAcao.id)]
    for esperado in ("OS_CRIADA", "OS_ATRIBUIDA", "OS_PAUSADA", "OS_CANCELADA"):
        assert esperado in acoes
    cancelamento = db.query(LogAcao).filter(LogAcao.acao == "OS_CANCELADA").one()
    assert cancelamento.papel == "admin" and cancelamento.id_usuario == fluxo.admin.id
