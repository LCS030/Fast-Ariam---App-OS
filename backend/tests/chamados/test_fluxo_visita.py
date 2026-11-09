"""
Fluxo normal da visita: T-01, T-21, T-07, T-19, RN-17/RN-18 e km_total (RN-19).
"""
from datetime import datetime, timedelta, timezone

from app.services.tempo import hhmm_negocio
from chamados.helpers import imagem


def _fluxo_completo(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa(1000, 1020)
    assert fluxo.iniciar_atendimento().status_code == 200
    r = fluxo.servico(materiais=[{"nome": "Compressor", "quantidade": 1, "valor": 850.0}])
    assert r.status_code == 200, r.text  # v0.5: o registro de serviço já existe; o técnico o preenche por PATCH
    servico_id = r.json()["id_servico"]
    for tipo, tam in (("defeito", (300, 200)), ("conserto", (1000, 1300))):
        r = fluxo.c.post(fluxo.url(f"servicos/{servico_id}/upload-foto"), headers=fluxo.tecnico.headers,
                         data={"tipo": tipo}, files={"file": imagem(*tam)})
        assert r.status_code == 200, r.text
    assert fluxo.finalizar_atendimento().status_code == 200
    return fluxo.volta_completa(1020, 1045)


def test_t01_t21_fluxo_normal_finaliza_automaticamente_e_congela_custo(fluxo, db):
    """T-01 / T-21: volta sem pausa -> Finalizado + data_conclusao + servico_finalizado + custo congelado."""
    r = _fluxo_completo(fluxo)
    assert r.status_code == 200, r.text
    visita = r.json()
    assert visita["servico_finalizado"] is True
    assert visita["km_total"] == (1020 - 1000) + (1045 - 1020)
    assert visita["volta_fim_em"] is not None and visita["ida_inicio_em"] is not None

    os_ = fluxo.os()
    assert os_["status"] == "Finalizado"
    assert os_["data_conclusao"] is not None

    custo = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers)
    assert custo.status_code == 200
    corpo = custo.json()
    assert corpo["congelado"] is True
    assert corpo["id_os"] == fluxo.os_id
    assert corpo["detalhes_por_visita"][0]["id_visita"] == fluxo.visita_id
    assert corpo["custo_total_materiais"] == 850.0
    assert corpo["custo_total_km"] == round(45 * 1.15, 2)

    from app.models.custo_os import CustoOS
    db.expire_all()
    assert db.get(CustoOS, fluxo.os_id) is not None


def test_nao_ha_concluir_manual(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/concluir", headers=fluxo.tecnico.headers)
    assert r.status_code in (404, 405)


def test_rn17_iniciar_atendimento_exige_ida_finalizada(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    r = fluxo.iniciar_atendimento()
    assert r.status_code == 400
    assert "ida" in r.json()["detail"].lower()
    fluxo.iniciar("ida", 100)
    r = fluxo.iniciar_atendimento()  # ida iniciada mas não finalizada
    assert r.status_code == 400
    assert fluxo.os()["status"] == "Agendado"


def test_atalho_iniciar_atendimento_da_os_tambem_exige_ida_e_agendado(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/iniciar-atendimento", headers=fluxo.tecnico.headers)
    assert r.status_code == 400
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()  # v0.5 (TR-12): foto de defeito de cada equipamento antes de iniciar
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/iniciar-atendimento", headers=fluxo.tecnico.headers)
    assert r.status_code == 200 and r.json()["status"] == "Em Atendimento"
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/iniciar-atendimento", headers=fluxo.tecnico.headers)
    assert r.status_code == 409  # já está Em Atendimento


def test_atalho_iniciar_atendimento_nao_aceita_pendente(fluxo, outro_tecnico):
    fluxo.criar_os(com_tecnico=False)
    # Pendente não tem técnico: qualquer técnico recebe 403 (não é o atribuído) e o status não muda.
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/iniciar-atendimento", headers=fluxo.tecnico.headers)
    assert r.status_code == 403
    assert fluxo.os()["status"] == "Pendente"


def test_rn18_volta_so_depois_do_atendimento(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.iniciar("volta", 1020)
    assert r.status_code == 400
    assert "Finalize o atendimento" in r.json()["detail"]


def test_ida_nao_inicia_duas_vezes_e_ordem_das_etapas(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    assert fluxo.finalizar("ida", 10).status_code == 400  # não iniciada
    assert fluxo.iniciar("ida", 10).status_code == 200
    assert fluxo.iniciar("ida", 10).status_code == 400  # duplicada
    assert fluxo.finalizar("ida", 5).status_code == 400  # km_fim < km_inicio
    assert fluxo.finalizar("ida", 30).status_code == 200
    assert fluxo.finalizar("ida", 30).status_code == 400  # já finalizada


def test_estado_da_visita_acompanha_o_fluxo(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    e = fluxo.estado()
    assert e["pode_iniciar_deslocamento_ida"] and not e["pode_iniciar_atendimento"]
    fluxo.iniciar("ida", 10)
    e = fluxo.estado()
    assert e["pode_finalizar_deslocamento_ida"] and not e["pode_iniciar_deslocamento_ida"]
    fluxo.finalizar("ida", 20)
    # v0.5 (TR-12): com a ida finalizada mas sem foto de defeito, o início fica bloqueado e o estado explica por quê
    e = fluxo.estado()
    assert e["pode_iniciar_atendimento"] is False and e["pode_registrar_foto_defeito"] is True
    assert "foto do defeito" in e["bloqueio_iniciar_atendimento"]
    assert [q["foto_defeito"] for q in e["equipamentos"]] == [False]
    fluxo.fotos_defeito_todas()
    e = fluxo.estado()
    assert e["pode_iniciar_atendimento"] is True and e["bloqueio_iniciar_atendimento"] is None
    fluxo.iniciar_atendimento()
    e = fluxo.estado()
    assert e["atendimento_em_andamento"] is True and e["pode_pausar_os"]
    # TR-13: finalizar exige conserto salvo + foto de conserto
    assert e["pode_finalizar_atendimento"] is False and "conserto" in e["bloqueio_finalizar_atendimento"]
    fluxo.conserto_completo(estrito=True)
    e = fluxo.estado()
    assert e["pode_finalizar_atendimento"] is True and e["bloqueio_finalizar_atendimento"] is None
    assert e["pode_iniciar_deslocamento_volta"] is False


def test_t07_comprovante_de_pedagio_obrigatorio_ao_finalizar(fluxo):
    """T-07: pedágio > 0 sem comprovante -> 400 ao finalizar a volta; com comprovante em `comprovante` -> ok."""
    fluxo.ate_em_atendimento()
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}", json={"valor_pedagio": 9.8},
                      headers=fluxo.tecnico.headers)
    assert r.status_code == 200 and r.json()["valor_pedagio"] == 9.8
    assert fluxo.finalizar_atendimento().status_code == 200
    r = fluxo.volta_completa()
    assert r.status_code == 400
    assert "pedágio" in r.json()["detail"].lower()
    assert fluxo.os()["status"] == "Em Atendimento"  # nada mudou

    up = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers,
                      data={"file_type": "comprovante_pedagio_urls"}, files={"file": imagem(300, 200)})
    assert up.status_code == 200, up.text
    assert len(up.json()["comprovante_pedagio_urls"]) == 1
    r = fluxo.finalizar("volta", 1040)
    assert r.status_code == 200, r.text
    assert fluxo.os()["status"] == "Finalizado"


def test_rn20_frete_exige_comprovante(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.c.patch(f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}", json={"valor_frete_devolucao": 16.35},
                  headers=fluxo.tecnico.headers)
    fluxo.finalizar_atendimento()
    r = fluxo.volta_completa()
    assert r.status_code == 400 and "frete" in r.json()["detail"].lower()


def test_rn19_odometro_obrigatorio_quando_km_total_maior_que_zero(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.finalizar_atendimento()
    r = fluxo.volta_completa(foto_fim=False)  # sem a foto do odômetro final
    assert r.status_code == 400
    assert "odômetro" in r.json()["detail"].lower()
    assert fluxo.foto_deslocamento("volta", "fim").status_code == 200
    assert fluxo.finalizar("volta", 1040).status_code == 200


def test_volta_com_km_total_zero_nao_exige_foto_de_odometro(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.iniciar("ida", 500)
    fluxo.finalizar("ida", 500)
    fluxo.iniciar_atendimento()
    fluxo.finalizar_atendimento()
    fluxo.iniciar("volta", 500)
    r = fluxo.finalizar("volta", 500)
    assert r.status_code == 200 and r.json()["km_total"] == 0
    assert fluxo.os()["status"] == "Finalizado"


def test_volta_sem_iniciar_retorna_400(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.finalizar_atendimento()
    assert fluxo.finalizar("volta", 10).status_code == 400


def test_t19_ocorrido_em_do_aparelho_e_gravado(fluxo):
    """T-19 / PR-30: o horário gravado é o do aparelho (TIMESTAMPTZ) e HH:mm legado derivado."""
    fluxo.criar_os()
    fluxo.criar_visita()
    ocorrido = datetime.now(timezone(timedelta(hours=-3))) - timedelta(hours=3)
    r = fluxo.iniciar("ida", 100, ocorrido_em=ocorrido.isoformat())
    assert r.status_code == 200, r.text
    visita = fluxo.c.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers).json()["visitas"][0]
    gravado = datetime.fromisoformat(visita["ida_inicio_em"])
    if gravado.tzinfo is None:  # SQLite devolve sem fuso
        gravado = gravado.replace(tzinfo=timezone.utc)
    assert abs((gravado - ocorrido).total_seconds()) < 1
    assert visita["hora_inicio_ida"] == hhmm_negocio(ocorrido)  # D6: HH:mm legado no fuso de negócio


def test_ocorrido_em_futuro_ou_sem_fuso_e_rejeitado(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    futuro = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    assert fluxo.iniciar("ida", 1, ocorrido_em=futuro).status_code == 422
    assert fluxo.iniciar("ida", 1, ocorrido_em="2026-10-29T14:02:11").status_code == 422
    # dentro da tolerância de 5 minutos é aceito
    quase = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
    assert fluxo.iniciar("ida", 1, ocorrido_em=quase).status_code == 200


def test_fim_antes_do_inicio_e_rejeitado(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    agora = datetime.now(timezone.utc)
    assert fluxo.iniciar("ida", 1, ocorrido_em=agora.isoformat()).status_code == 200
    antes = (agora - timedelta(hours=1)).isoformat()
    assert fluxo.finalizar("ida", 5, ocorrido_em=antes).status_code == 400
