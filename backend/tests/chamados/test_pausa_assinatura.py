"""
Pausa (T-11, T-12, RN-26/RN-29/RN-30) e finalização do atendimento com assinatura (T-15, RN-22/RN-23, PR-10/PR-35).
"""
import base64

import pytest

from app.models.pausa import Pausa
from app.models.visita import Visita
from chamados.helpers import CPF_VALIDO, CPF_VALIDO_DIGITOS, assinatura_b64, db_os


# ---------------------------------------------------------------------------------------------------------------------
# Pausa
# ---------------------------------------------------------------------------------------------------------------------
def test_t12_motivo_fora_da_lista_da_422(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.pausar("Almoço")
    assert r.status_code == 422
    assert fluxo.os()["status"] == "Em Atendimento"


@pytest.mark.parametrize("motivo", ["Peça pendente", "Cliente ausente", "Condições inseguras", "Aguardando aprovação"])
def test_motivos_oficiais_sem_descricao_sao_aceitos(fluxo, motivo):
    fluxo.ate_em_atendimento()
    r = fluxo.pausar(motivo)
    assert r.status_code == 200, r.text
    assert r.json()["motivo"] == motivo and r.json()["is_ativa"] is True


def test_t11_admin_pausa_outro_exige_descricao(fluxo, db):
    fluxo.ate_em_atendimento()
    r = fluxo.pausar("Outro", headers=fluxo.admin.headers)
    assert r.status_code == 422
    r = fluxo.pausar("Outro", descricao="   ", headers=fluxo.admin.headers)
    assert r.status_code == 422
    r = fluxo.pausar("Outro", descricao="Aguardando liberação do síndico", headers=fluxo.admin.headers)
    assert r.status_code == 200, r.text
    assert r.json()["por_papel"] == "admin" and r.json()["por_usuario_id"] == fluxo.admin.id
    assert fluxo.os()["status"] == "Pausado"
    db.expire_all()
    pausa = db.query(Pausa).one()
    assert pausa.por_papel == "admin" and pausa.por_usuario_id == fluxo.admin.id


def test_tecnico_pausa_grava_autor_e_papel(fluxo, db):
    fluxo.ate_em_atendimento()
    assert fluxo.pausar("Cliente ausente").status_code == 200
    db.expire_all()
    pausa = db.query(Pausa).one()
    assert pausa.por_papel == "tecnico" and pausa.por_usuario_id == fluxo.tecnico.id


def test_nao_pausa_duas_vezes(fluxo):
    fluxo.ate_em_atendimento()
    assert fluxo.pausar().status_code == 200
    r = fluxo.pausar()
    assert r.status_code == 400 and "pausada" in r.json()["detail"].lower()


def test_rn26_so_pausa_visita_em_atendimento(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    assert fluxo.pausar().status_code == 400  # atendimento não iniciado
    fluxo.ida_completa()
    assert fluxo.pausar().status_code == 400  # ida finalizada mas atendimento não iniciado


def test_rn26_nao_pausa_visita_com_atendimento_finalizado(fluxo):
    fluxo.ate_em_atendimento()
    assert fluxo.finalizar_atendimento().status_code == 200
    assert fluxo.pausar().status_code == 400


def test_pausa_de_tecnico_de_outra_os_e_403_e_de_admin_permitida(fluxo, outro_tecnico):
    fluxo.ate_em_atendimento()
    assert fluxo.pausar(headers=outro_tecnico.headers).status_code == 403
    assert fluxo.pausar(headers=fluxo.admin.headers).status_code == 200


def test_estado_reflete_pausa_e_bloqueia_finalizar_atendimento(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.pausar("Condições inseguras")
    e = fluxo.estado()
    assert e["is_os_pausada"] is True and e["motivo_pausa"] == "Condições inseguras"
    assert e["pode_finalizar_atendimento"] is False and e["pode_pausar_os"] is False
    assert e["pode_iniciar_deslocamento_volta"] is True  # RN-18: com pausa, volta liberada


def test_nao_existe_retomar_pausa(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.pausar()
    for rota in ("retomar", "resolver-pausa"):
        assert fluxo.post(rota, {}).status_code in (404, 405)
    # PATCH do status para Em Atendimento (retomada) e proibido (TR-03)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"status": "Em Atendimento"}, headers=fluxo.admin.headers)
    assert r.status_code == 409


# ---------------------------------------------------------------------------------------------------------------------
# Finalizar atendimento / assinatura / CPF
# ---------------------------------------------------------------------------------------------------------------------
def test_t15_cpf_invalido_da_422_e_nada_e_gravado(fluxo, db):
    fluxo.ate_em_atendimento()
    for cpf in ("111.111.111-11", "123", "529.982.247-26", "abc"):
        r = fluxo.finalizar_atendimento(cpf=cpf)
        assert r.status_code == 422, (cpf, r.text)
    assert "CPF inválido" in fluxo.finalizar_atendimento(cpf="111.111.111-11").json()["detail"]
    db.expire_all()
    visita = db.get(Visita, fluxo.visita_id)
    assert visita.assinatura_url is None and visita.documento_cliente is None and visita.atendimento_fim_em is None


def test_t15_cpf_valido_grava_onze_digitos_na_visita_e_nao_na_os(fluxo, db):
    fluxo.ate_em_atendimento()
    r = fluxo.finalizar_atendimento(cpf=CPF_VALIDO, nome="Maria Gerente")
    assert r.status_code == 200, r.text
    url = r.json()["assinatura_url"]
    assert url.startswith("/static/assinaturas/")
    db.expire_all()
    visita = db.get(Visita, fluxo.visita_id)
    assert visita.documento_cliente == CPF_VALIDO_DIGITOS
    assert visita.nome_cliente_assinatura == "Maria Gerente"
    assert visita.assinatura_url == url
    assert visita.atendimento_fim_em is not None and visita.hora_fim_atendimento
    assert db_os(db, fluxo.os_id).assinatura_cliente_url is None  # PR-35: nunca na OS
    assert db_os(db, fluxo.os_id).status.value == "Em Atendimento"  # status só muda na volta


def test_finalizar_atendimento_com_pausa_ativa_da_400(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.pausar()
    r = fluxo.finalizar_atendimento()
    assert r.status_code == 400 and "pausada" in r.json()["detail"]


def test_finalizar_atendimento_sem_iniciar_ou_duas_vezes_da_400(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa()
    assert fluxo.finalizar_atendimento().status_code == 400  # não iniciado
    fluxo.iniciar_atendimento()
    assert fluxo.finalizar_atendimento().status_code == 200
    assert fluxo.finalizar_atendimento().status_code == 400  # já finalizado


def test_assinatura_base64_invalida_nao_e_500(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.finalizar_atendimento(assinatura="isto-nao-e-base64!!!")
    assert r.status_code == 400
    r = fluxo.finalizar_atendimento(assinatura=base64.b64encode(b"nao sou uma imagem").decode())
    assert r.status_code == 400
    r = fluxo.finalizar_atendimento(assinatura="data:image/png;base64,")
    assert r.status_code in (400, 422)


def test_assinatura_aceita_com_ou_sem_prefixo_data_uri(fluxo):
    fluxo.ate_em_atendimento()
    assert fluxo.finalizar_atendimento(assinatura=assinatura_b64(com_prefixo=False)).status_code == 200


def test_assinatura_acima_de_15mb_da_413(fluxo, monkeypatch):
    from app.services import file_service
    fluxo.ate_em_atendimento()
    monkeypatch.setattr(file_service, "MAX_IMAGE_BYTES", 1024)
    r = fluxo.finalizar_atendimento(assinatura=base64.b64encode(b"\x89PNG" + b"0" * 5000).decode())
    assert r.status_code == 413


def test_campos_obrigatorios_ausentes_da_422(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.post("finalizar-atendimento", {"nome_cliente": "x"})
    assert r.status_code == 422


def test_admin_nao_finaliza_atendimento(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.post(
        "finalizar-atendimento",
        {"nome_cliente": "x", "documento_cliente": CPF_VALIDO, "assinatura_base64": assinatura_b64()},
        headers=fluxo.admin.headers)
    assert r.status_code == 403


def test_finalizar_dados_foi_descontinuado(fluxo):
    fluxo.ate_em_atendimento()
    r = fluxo.post("finalizar-dados", {"nome_cliente": "x", "documento_cliente": CPF_VALIDO})
    assert r.status_code == 410
