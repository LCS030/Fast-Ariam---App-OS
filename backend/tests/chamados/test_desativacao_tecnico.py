"""
RN-08a (aprovada): desativar técnico desatribui TODAS as OS não finalizadas e não canceladas (-> Pendente, sem técnico),
preservando o histórico; reatribuição cria visita nova quando a anterior já foi iniciada. T-17.
"""
from app.models.chamado import OrdemServico
from app.models.custo_os import CustoOS
from app.models.log_acao import LogAcao
from app.models.pausa import Pausa
from app.models.visita import Visita
from chamados.helpers import Fluxo, criar_usuario, imagem


def _novo(fluxo, tecnico=None) -> Fluxo:
    return Fluxo(fluxo.c, fluxo.admin, tecnico or fluxo.tecnico, fluxo.cliente_id)


def _agendada(f):
    f.criar_os()
    f.criar_visita()
    return f


def _em_atendimento(f):
    return f.ate_em_atendimento()


def _pausada(f):
    f.ate_em_atendimento()
    assert f.pausar("Peça pendente").status_code == 200
    return f


def _aguardando(f):
    _pausada(f)
    f.iniciar("volta", 1020)
    f.foto_deslocamento("volta", "fim")
    assert f.finalizar("volta", 1040).status_code == 200
    assert f.os()["status"] == "Aguardando Reagendamento"
    return f


def _finalizada(f):
    f.ate_em_atendimento()
    f.finalizar_atendimento()
    assert f.volta_completa().status_code == 200
    assert f.os()["status"] == "Finalizado"
    return f


def _cancelada(f):
    f.criar_os()
    assert f.c.post(f"/api/chamados/{f.os_id}/cancelar", headers=f.admin.headers, json={"motivo": "x"}).status_code == 200
    return f


def _desativar(fluxo, tecnico_id=None, via_patch=False):
    tid = tecnico_id or fluxo.tecnico.id
    if via_patch:
        return fluxo.c.patch(f"/api/tecnicos/{tid}", json={"is_active": False}, headers=fluxo.admin.headers)
    return fluxo.c.delete(f"/api/tecnicos/{tid}", headers=fluxo.admin.headers)


def _cenario(fluxo, outro_tecnico):
    f = {nome: _novo(fluxo) for nome in ("agendada", "atendimento", "pausada", "aguardando", "finalizada", "cancelada")}
    _agendada(f["agendada"])
    _em_atendimento(f["atendimento"])
    _pausada(f["pausada"])
    _aguardando(f["aguardando"])
    _finalizada(f["finalizada"])
    _cancelada(f["cancelada"])
    f["outro"] = _novo(fluxo, outro_tecnico)
    f["outro"].criar_os()
    return f


def _verificar_desativacao(fluxo, db, f):
    nao_finalizadas = ("agendada", "atendimento", "pausada", "aguardando")
    for nome in nao_finalizadas:
        os_ = f[nome].os()
        assert os_["status"] == "Pendente" and os_["id_tecnico_atribuido"] is None, nome
        assert len(os_["visitas"]) >= 1, nome  # histórico preservado
    # Finalizada: intacta (técnico, status, custo congelado)
    fin = f["finalizada"].os()
    assert fin["status"] == "Finalizado" and fin["id_tecnico_atribuido"] == fluxo.tecnico.id
    db.expire_all()
    assert db.get(CustoOS, f["finalizada"].os_id) is not None
    # Cancelada: intacta
    canc = db.get(OrdemServico, f["cancelada"].os_id)
    assert canc.is_cancelled is True and canc.id_tecnico_atribuido == fluxo.tecnico.id
    # OS de outro técnico: intacta
    outro = f["outro"].os()
    assert outro["status"] == "Agendado" and outro["id_tecnico_atribuido"] == f["outro"].tecnico.id

    # pausas preservadas, porém encerradas (decisão registrada)
    for nome in ("pausada", "aguardando"):
        pausas = db.query(Pausa).filter(Pausa.visita_id == f[nome].visita_id).all()
        assert len(pausas) == 1 and pausas[0].is_ativa is False and pausas[0].encerrada_em is not None, nome

    # auditoria: admin, uma linha por OS afetada, com os ids no payload
    ids = sorted(f[n].os_id for n in nao_finalizadas)
    logs = db.query(LogAcao).filter(LogAcao.acao == "DESATRIBUIDA_POR_DESATIVACAO").all()
    assert sorted(l.id_os for l in logs) == ids
    for l in logs:
        assert l.papel == "admin" and l.id_usuario == fluxo.admin.id
        assert l.payload["ids_os"] == ids and l.payload["id_tecnico"] == fluxo.tecnico.id
    assert {l.payload["status_anterior"] for l in logs} == {
        "Agendado", "Em Atendimento", "Pausado", "Aguardando Reagendamento"}


def test_t17_delete_desatribui_todas_as_os_nao_finalizadas(fluxo, db, outro_tecnico):
    f = _cenario(fluxo, outro_tecnico)
    token_do_tecnico = fluxo.tecnico.headers
    assert _desativar(fluxo).status_code == 204
    _verificar_desativacao(fluxo, db, f)
    # sessão do técnico desativado cai (SEG-01)
    assert fluxo.c.get("/api/chamados/", headers=token_do_tecnico).status_code == 401


def test_t17_patch_is_active_false_tem_o_mesmo_efeito(fluxo, db, outro_tecnico):
    f = _cenario(fluxo, outro_tecnico)
    assert _desativar(fluxo, via_patch=True).status_code == 200
    _verificar_desativacao(fluxo, db, f)


def test_patch_que_nao_desativa_nao_desatribui(fluxo, db):
    fluxo.criar_os()
    r = fluxo.c.patch(f"/api/tecnicos/{fluxo.tecnico.id}", json={"telefone": "(27) 98888-7777"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200
    assert fluxo.os()["id_tecnico_atribuido"] == fluxo.tecnico.id
    assert db.query(LogAcao).filter(LogAcao.acao == "DESATRIBUIDA_POR_DESATIVACAO").count() == 0


def test_desativar_duas_vezes_e_idempotente(fluxo, db):
    fluxo.criar_os()
    assert _desativar(fluxo).status_code == 204
    assert _desativar(fluxo).status_code == 204
    db.expire_all()
    assert db.query(LogAcao).filter(LogAcao.acao == "DESATRIBUIDA_POR_DESATIVACAO").count() == 1


def test_tecnico_sem_os_desativa_sem_log(fluxo, db):
    assert _desativar(fluxo).status_code == 204
    assert db.query(LogAcao).filter(LogAcao.acao == "DESATRIBUIDA_POR_DESATIVACAO").count() == 0


def test_admin_nao_desativa_a_si_mesmo_e_desativar_outro_admin_nao_desatribui(fluxo, db):
    fluxo.criar_os()
    assert _desativar(fluxo, fluxo.admin.id).status_code == 400  # guarda mantida
    outro_admin = criar_usuario(db, "admin")
    assert _desativar(fluxo, outro_admin.id).status_code == 204
    assert fluxo.os()["id_tecnico_atribuido"] == fluxo.tecnico.id
    assert db.query(LogAcao).filter(LogAcao.acao == "DESATRIBUIDA_POR_DESATIVACAO").count() == 0


def test_admin_nao_recebe_os(fluxo):
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x",
                           "equipamentos": fluxo.novos_equipamentos(), "id_tecnico_atribuido": fluxo.admin.id})
    assert r.status_code == 400
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": fluxo.admin.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 400


# ---------------------------------------------------------------------------------------------------------------------
# Reatribuição depois da desativação
# ---------------------------------------------------------------------------------------------------------------------
def _atribuir(fluxo, novo):
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": novo.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_reatribuir_com_visita_iniciada_cria_visita_nova_do_zero(fluxo, db, outro_tecnico):
    fluxo.ate_em_atendimento()  # técnico antigo iniciou ida e atendimento (visita 1)
    antiga = fluxo.visita_id
    assert _desativar(fluxo).status_code == 204
    assert fluxo.os()["status"] == "Pendente"

    os_ = _atribuir(fluxo, outro_tecnico)
    assert os_["status"] == "Agendado" and os_["id_tecnico_atribuido"] == outro_tecnico.id
    assert len(os_["visitas"]) == 2
    velha = next(v for v in os_["visitas"] if v["id_visita"] == antiga)
    nova = next(v for v in os_["visitas"] if v["id_visita"] != antiga)
    # a antiga fica como histórico, intacta
    assert velha["ida_inicio_em"] is not None and velha["atendimento_inicio_em"] is not None
    assert velha["servico_finalizado"] is False
    # a nova parte do zero
    assert nova["servico_finalizado"] is False and nova["ida_inicio_em"] is None and nova["km_total"] == 0
    assert nova["atendimento_inicio_em"] is None and nova["pausas"] == []

    fluxo.tecnico = outro_tecnico
    # estado: a antiga não oferece nenhuma ação; a nova começa pela ida
    e_velha = fluxo.estado()  # visita_id ainda é a antiga
    assert e_velha["visita_vigente"] is False
    assert not any(v for k, v in e_velha.items() if k.startswith("pode_") and k != "pode_concluir_chamado")
    # ações de campo na visita antiga são recusadas
    assert fluxo.iniciar("ida", 1).status_code == 409
    assert fluxo.iniciar_atendimento().status_code == 409
    assert fluxo.pausar().status_code == 409
    assert fluxo.servico().status_code == 409
    # POST /visitas não duplica a visita aberta
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/visitas", json={"data_visita": "2030-01-01"},
                     headers=fluxo.admin.headers)
    assert r.status_code == 409

    # o novo técnico executa tudo na visita nova até Finalizado
    fluxo.visita_id = nova["id_visita"]
    e_nova = fluxo.estado()
    assert e_nova["visita_vigente"] is True and e_nova["pode_iniciar_deslocamento_ida"] is True
    fluxo.ida_completa(5000, 5010)
    assert fluxo.iniciar_atendimento().status_code == 200
    assert fluxo.finalizar_atendimento().status_code == 200
    assert fluxo.volta_completa(5010, 5030).status_code == 200
    os_final = fluxo.os()
    assert os_final["status"] == "Finalizado" and len(os_final["visitas"]) == 2

    # custo: a visita abandonada conta só o que foi registrado (D7: atendimento sem fim = 0 de serviço)
    custo = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()
    por_visita = {d["id_visita"]: d for d in custo["detalhes_por_visita"]}
    assert set(por_visita) == {antiga, nova["id_visita"]}
    abandonada = por_visita[antiga]
    assert abandonada["custo_tempo_servico"] == 0.0
    assert abandonada["custo_km"] == round(20 * custo["valores_utilizados"]["quilometragem"], 2)  # só a ida registrada
    assert por_visita[nova["id_visita"]]["custo_km"] == round(30 * custo["valores_utilizados"]["quilometragem"], 2)
    assert custo["congelado"] is True


def test_reatribuir_com_visita_nao_iniciada_reaproveita_a_visita(fluxo, outro_tecnico):
    fluxo.criar_os()
    fluxo.criar_visita()
    visita = fluxo.visita_id
    _desativar(fluxo)
    os_ = _atribuir(fluxo, outro_tecnico)
    assert [v["id_visita"] for v in os_["visitas"]] == [visita]
    assert os_["status"] == "Agendado"


def test_reatribuir_apos_aguardando_reagendamento_cria_visita_nova(fluxo, outro_tecnico):
    _aguardando(fluxo)
    antiga = fluxo.visita_id
    _desativar(fluxo)
    os_ = _atribuir(fluxo, outro_tecnico)
    assert len(os_["visitas"]) == 2
    abertas = [v for v in os_["visitas"] if not v["servico_finalizado"]]
    assert len(abertas) == 1 and abertas[0]["id_visita"] != antiga  # exatamente uma visita aberta executável


def test_reatribuir_a_tecnico_inativo_e_recusado(fluxo, db):
    fluxo.criar_os()
    _desativar(fluxo)
    inativo = criar_usuario(db, "tecnico", ativo=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": inativo.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 404
    assert fluxo.os()["status"] == "Pendente"


def test_os_pendente_nao_aceita_acoes_na_visita_abandonada(fluxo, db):
    fluxo.ate_em_atendimento()
    _desativar(fluxo)
    # mesmo um admin consultando: nenhum botão disponível enquanto a OS está Pendente
    e = fluxo.estado(headers=fluxo.admin.headers)
    assert e["visita_vigente"] is False and e["pode_finalizar_atendimento"] is False and e["pode_pausar_os"] is False
    # e o reagendamento recusa (Pendente)
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": "2099-01-01"})
    assert r.status_code == 409
