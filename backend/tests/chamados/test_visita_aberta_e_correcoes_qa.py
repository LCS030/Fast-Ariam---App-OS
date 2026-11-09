"""
Correções do QA/Security (D1, D5, D6, D11, D12, D13, M4, A2): visita aberta automática, pausas na resposta, fuso de
negócio, travas, uploads em OS Finalizada, config e nosniff.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError

from app.models.chamado import OrdemServico
from app.models.log_acao import LogAcao
from app.models.tecnico import Tecnico
from app.models.visita import Visita
from app.repositories.supabase_repository import SQLRepository
from app.schemas.base_schemas import StatusChamado
from app.services import custo_service
from app.services.tempo import data_negocio, hhmm_negocio, hoje_negocio
from chamados.helpers import Fluxo, imagem, futuro

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _os_sem_descer_pelo_helper(fluxo, **extra):
    """Cria a OS pela API SEM usar `criar_visita` e adota a visita aberta devolvida na própria criação."""
    os_ = fluxo.criar_os(**extra)
    assert len(os_["visitas"]) == 1 and os_["visitas"][0]["servico_finalizado"] is False
    fluxo.visita_id = os_["visitas"][0]["id_visita"]
    return os_


# ---------------------------------------------------------------------------------------------------------------------
# D1: toda OS Agendado tem exatamente uma visita aberta
# ---------------------------------------------------------------------------------------------------------------------
def test_d1_fluxo_completo_sem_criar_visita_ate_finalizado(fluxo):
    _os_sem_descer_pelo_helper(fluxo)
    fluxo.ida_completa(1000, 1020)
    assert fluxo.iniciar_atendimento().status_code == 200
    assert fluxo.finalizar_atendimento().status_code == 200
    r = fluxo.volta_completa(1020, 1050)
    assert r.status_code == 200, r.text
    os_ = fluxo.os()
    assert os_["status"] == "Finalizado" and len(os_["visitas"]) == 1
    assert os_["visitas"][0]["km_total"] == 50


def test_d1_fluxo_com_pausa_reagendamento_e_segunda_visita(fluxo):
    _os_sem_descer_pelo_helper(fluxo)
    primeira = fluxo.visita_id
    fluxo.ida_completa(1000, 1020)
    assert fluxo.iniciar_atendimento().status_code == 200
    assert fluxo.pausar("Peça pendente").status_code == 200
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")
    assert fluxo.finalizar("volta", 1040).status_code == 200
    assert fluxo.os()["status"] == "Aguardando Reagendamento"

    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": futuro(7)})
    assert r.status_code == 201, r.text
    segunda = r.json()["id_visita"]
    assert segunda != primeira
    abertas = [v for v in fluxo.os()["visitas"] if not v["servico_finalizado"]]
    assert [v["id_visita"] for v in abertas] == [segunda]  # exatamente uma visita aberta

    fluxo.visita_id = segunda
    fluxo.ida_completa(2000, 2010)
    assert fluxo.iniciar_atendimento().status_code == 200
    assert fluxo.finalizar_atendimento(nome="Segundo").status_code == 200
    assert fluxo.volta_completa(2010, 2020).status_code == 200
    os_ = fluxo.os()
    assert os_["status"] == "Finalizado" and len(os_["visitas"]) == 2

    # D5: o histórico de pausas vem na visita
    v1 = next(v for v in os_["visitas"] if v["id_visita"] == primeira)
    assert len(v1["pausas"]) == 1
    p = v1["pausas"][0]
    assert p["motivo"] == "Peça pendente" and p["is_ativa"] is False and p["encerrada_em"] is not None
    assert p["por_papel"] == "tecnico" and p["por_usuario_id"] == fluxo.tecnico.id
    assert p["visita_id"] == primeira and p["id_pausa"] and p["criado_em"]


def test_d1_criar_com_tecnico_usa_data_agendamento_ou_hoje(fluxo):
    os_ = fluxo.criar_os(data_agendamento=futuro(5))
    assert os_["visitas"][0]["data_visita"] == futuro(5)
    os2 = fluxo.criar_os()
    assert os2["visitas"][0]["data_visita"] == hoje_negocio().isoformat()


def test_d1_os_pendente_nao_tem_visita_e_atribuir_cria_uma(fluxo):
    os_ = fluxo.criar_os(com_tecnico=False)
    assert os_["visitas"] == []
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": fluxo.tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "Agendado" and len(r.json()["visitas"]) == 1
    assert r.json()["visitas"][0]["data_visita"] == hoje_negocio().isoformat()
    assert r.json()["data_agendamento"] == hoje_negocio().isoformat()
    # reatribuir depois não cria outra visita
    r2 = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"descricao_cliente": "x"}, headers=fluxo.admin.headers)
    assert len(r2.json()["visitas"]) == 1


def test_d1_atribuir_com_data_agendamento_usa_a_data(fluxo):
    fluxo.criar_os(com_tecnico=False)
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}",
                      json={"id_tecnico_atribuido": fluxo.tecnico.id, "data_agendamento": futuro(4)},
                      headers=fluxo.admin.headers)
    assert r.json()["visitas"][0]["data_visita"] == futuro(4)


def test_d1_post_visitas_nao_duplica_visita_aberta(fluxo):
    fluxo.criar_os()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/visitas", json={"data_visita": futuro(3)},
                     headers=fluxo.admin.headers)
    assert r.status_code == 409 and "visita aberta" in r.json()["detail"]
    assert len(fluxo.os()["visitas"]) == 1


def _os_agendada_legada_sem_visita(db, fluxo) -> int:
    """OS Agendado SEM visita (dado legado, anterior ao D1), inserida direto no banco."""
    os_ = OrdemServico(id_cliente=fluxo.cliente_id, id_tecnico_atribuido=fluxo.tecnico.id, status=StatusChamado.AGENDADO,
                       data_abertura=hoje_negocio(), descricao_cliente="legada", is_cancelled=False)
    db.add(os_)
    db.commit()
    # v0.5: toda OS tem equipamento (TR-15). Esta OS é legada só quanto à VISITA, então ganha um equipamento.
    from app.models.equipamento_modelo import EquipamentoModelo
    from app.models.os_equipamento import OsEquipamento
    modelo = EquipamentoModelo(modelo="Modelo legado de teste")
    db.add(modelo)
    db.commit()
    db.add(OsEquipamento(id_os=os_.id_os, id_equipamento_modelo=modelo.id_equipamento_modelo, numero_serie="LEG-1"))
    db.commit()
    fluxo.os_id = os_.id_os
    return os_.id_os


def test_d1_reagendar_agendado_legado_sem_visita_cria_a_visita(fluxo, db):
    _os_agendada_legada_sem_visita(db, fluxo)
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": futuro(6)})
    assert r.status_code == 201, r.text
    assert r.json()["data_visita"] == futuro(6) and r.json()["servico_finalizado"] is False
    os_ = fluxo.os()
    assert len(os_["visitas"]) == 1 and os_["data_agendamento"] == futuro(6)


def test_d1_post_visitas_permitido_quando_nao_ha_visita_aberta(fluxo, db):
    _os_agendada_legada_sem_visita(db, fluxo)
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/visitas", json={"data_visita": futuro(2)},
                     headers=fluxo.tecnico.headers)
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------------------------------------------------
# D6: fuso de negócio
# ---------------------------------------------------------------------------------------------------------------------
def test_d6_datas_e_hhmm_no_fuso_de_sao_paulo():
    utc = datetime(2026, 11, 5, 1, 30, tzinfo=timezone.utc)  # 22:30 de 04/11 em São Paulo
    assert data_negocio(utc).isoformat() == "2026-11-04"
    assert hhmm_negocio(utc) == "22:30"
    assert data_negocio(utc.replace(tzinfo=None)).isoformat() == "2026-11-04"  # naive = UTC (SQLite)


def test_d6_hora_legada_e_data_conclusao_vem_do_fuso_de_negocio(fluxo):
    fluxo.criar_os()
    fluxo.visita_id = fluxo.os()["visitas"][0]["id_visita"]
    agora = datetime.now(timezone.utc)
    assert fluxo.iniciar("ida", 1, ocorrido_em=agora.isoformat()).status_code == 200
    visita = fluxo.os()["visitas"][0]
    assert visita["hora_inicio_ida"] == hhmm_negocio(agora)
    # *_em continua em UTC
    gravado = datetime.fromisoformat(visita["ida_inicio_em"])
    assert gravado.utcoffset() in (None, timedelta(0))
    fluxo.finalizar("ida", 1)
    fluxo.iniciar_atendimento()
    fluxo.finalizar_atendimento()
    fluxo.iniciar("volta", 1)
    assert fluxo.finalizar("volta", 1).status_code == 200
    assert fluxo.os()["data_conclusao"] == data_negocio(datetime.now(timezone.utc)).isoformat()
    assert fluxo.os()["data_abertura"] == hoje_negocio().isoformat()


def test_d6_ocorrido_em_futuro_tem_mensagem_clara(fluxo):
    fluxo.criar_os()
    fluxo.visita_id = fluxo.os()["visitas"][0]["id_visita"]
    futuro_dt = (datetime.now(timezone.utc) + timedelta(minutes=40)).isoformat()
    r = fluxo.iniciar("ida", 1, ocorrido_em=futuro_dt)
    assert r.status_code == 422
    msg = str(r.json()["detail"])
    assert "minutos no futuro" in msg and "relógio" in msg


# ---------------------------------------------------------------------------------------------------------------------
# D12 / D13
# ---------------------------------------------------------------------------------------------------------------------
def test_d12_admin_altera_data_da_visita_e_a_os_acompanha(fluxo):
    fluxo.criar_os()
    fluxo.visita_id = fluxo.os()["visitas"][0]["id_visita"]
    r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}", json={"data_visita": futuro(9)},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200
    assert fluxo.os()["data_agendamento"] == futuro(9)


def test_d13_pedagio_e_frete_nao_mudam_em_visita_encerrada(fluxo):
    _os_sem_descer_pelo_helper(fluxo)
    fluxo.ida_completa()
    fluxo.iniciar_atendimento()
    fluxo.pausar("Cliente ausente")
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")
    assert fluxo.finalizar("volta", 1040).status_code == 200
    assert fluxo.os()["status"] == "Aguardando Reagendamento"  # OS não Finalizada, mas a visita já encerrou
    url = f"/api/chamados/{fluxo.os_id}/visitas/{fluxo.visita_id}"
    for campo in ("valor_pedagio", "valor_frete_devolucao"):
        r = fluxo.c.patch(url, json={campo: 99.9}, headers=fluxo.admin.headers)
        assert r.status_code == 409, campo
    # campos que não afetam custo continuam editáveis
    assert fluxo.c.patch(url, json={"descricao_servico_executado": "ok"}, headers=fluxo.admin.headers).status_code == 200


def test_d13_reagendar_recusa_data_passada(fluxo):
    fluxo.criar_os()
    ontem = (hoje_negocio() - timedelta(days=1)).isoformat()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": ontem})
    assert r.status_code == 422
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": hoje_negocio().isoformat()})
    assert r.status_code == 200  # hoje é permitido


def test_d13_reagendar_exige_tecnico_ativo(fluxo, db):
    fluxo.criar_os()
    db.query(Tecnico).filter(Tecnico.id_tecnico == fluxo.tecnico.id).update({"is_active": False})
    db.commit()
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", headers=fluxo.admin.headers,
                     json={"data_visita": futuro(5)})
    assert r.status_code == 409 and "inativo" in r.json()["detail"]


# ---------------------------------------------------------------------------------------------------------------------
# M4: uploads em OS Finalizada e auditoria
# ---------------------------------------------------------------------------------------------------------------------
def _os_finalizada(fluxo):
    _os_sem_descer_pelo_helper(fluxo)
    fluxo.ida_completa()
    fluxo.iniciar_atendimento()
    servico_id = fluxo.servico().json()["id_servico"]
    fluxo.finalizar_atendimento()
    assert fluxo.volta_completa().status_code == 200
    assert fluxo.os()["status"] == "Finalizado"
    return servico_id


def test_m4_uploads_em_os_finalizada_retornam_409(fluxo):
    servico_id = _os_finalizada(fluxo)
    r = fluxo.foto_deslocamento("ida", "fim")
    assert r.status_code == 409
    r = fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers,
                     data={"file_type": "comprovante_frete_urls"}, files={"file": imagem(50, 50)})
    assert r.status_code == 409
    r = fluxo.c.post(fluxo.url(f"servicos/{servico_id}/upload-foto"), headers=fluxo.tecnico.headers,
                     data={"tipo": "defeito"}, files={"file": imagem(50, 50)})
    assert r.status_code == 409


def test_os_finalizada_nao_aceita_criar_nem_alterar_servico(fluxo):
    """Achado do QA (smoke): serviço/materiais de OS Finalizada divergiriam do custo congelado em custo_os."""
    servico_id = _os_finalizada(fluxo)
    r = fluxo.servico()
    assert r.status_code == 409
    r = fluxo.c.patch(fluxo.url(f"servicos/{servico_id}"), headers=fluxo.tecnico.headers,
                      json={"materiais_utilizados": [{"nome": "Alterado", "quantidade": 1, "valor": 1}]})
    assert r.status_code == 409


def test_m4_cada_upload_gera_log_acao_sem_pii(fluxo, db):
    _os_sem_descer_pelo_helper(fluxo)
    fluxo.ida_completa()
    fluxo.iniciar_atendimento()
    servico_id = fluxo.servico().json()["id_servico"]
    fluxo.c.post(fluxo.url("upload_file"), headers=fluxo.tecnico.headers,
                 data={"file_type": "comprovante_pedagio_urls"}, files={"file": imagem(50, 50)})
    fluxo.c.post(fluxo.url(f"servicos/{servico_id}/upload-foto"), headers=fluxo.tecnico.headers,
                 data={"tipo": "conserto"}, files={"file": imagem(1000, 1300)})
    db.expire_all()
    logs = db.query(LogAcao).filter(LogAcao.acao == "UPLOAD_ARQUIVO").all()
    campos = sorted(l.payload["campo"] for l in logs)
    # 1 do upload-deslocamento do ida_completa + comprovante + foto de conserto + foto de defeito
    # + 1 foto de defeito (pré-condição de iniciar o atendimento, v0.5)
    assert campos == ["comprovante_pedagio_urls", "foto_conserto", "foto_defeito", "foto_inicio_ida_url"]
    for l in logs:
        assert l.papel == "tecnico" and l.id_usuario == fluxo.tecnico.id
        assert set(l.payload) <= {"id_visita", "id_servico", "campo"}  # só ids e campo: sem nome/CPF/arquivo


# ---------------------------------------------------------------------------------------------------------------------
# D11: travas e idempotência
# ---------------------------------------------------------------------------------------------------------------------
def test_d11_consulta_de_travamento_usa_for_update_no_postgres():
    sql = str(SQLRepository.query_chamado_para_update(1).compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql and "ordem_servico" in sql


def _preparar_volta(fluxo):
    _os_sem_descer_pelo_helper(fluxo)
    fluxo.ida_completa()
    fluxo.iniciar_atendimento()
    fluxo.finalizar_atendimento()
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")


def test_d11_integrity_error_sem_finalizacao_efetiva_vira_409_e_nao_altera_nada(fluxo, db, monkeypatch):
    _preparar_volta(fluxo)

    def duplicado(*a, **k):
        raise IntegrityError("INSERT INTO custo_os", {}, Exception("duplicate key"))

    monkeypatch.setattr(custo_service, "congelar_custo", duplicado)
    r = fluxo.finalizar("volta", 1040)
    assert r.status_code == 409
    assert fluxo.os()["status"] == "Em Atendimento"


def test_d11_integrity_error_com_finalizacao_ja_efetivada_e_idempotente(fluxo, monkeypatch):
    """Simula a corrida: o commit grava a finalização e a violação de custo_os chega depois (outra requisição)."""
    _preparar_volta(fluxo)
    original = SQLRepository.commit
    estado = {"vezes": 0}

    def commit_e_falha(self):
        original(self)
        estado["vezes"] += 1
        if estado["vezes"] == 1:
            raise IntegrityError("INSERT INTO custo_os", {}, Exception("duplicate key"))

    monkeypatch.setattr(SQLRepository, "commit", commit_e_falha)
    r = fluxo.finalizar("volta", 1040)
    assert r.status_code == 200, r.text
    assert r.json()["servico_finalizado"] is True
    monkeypatch.undo()
    assert fluxo.os()["status"] == "Finalizado"


def test_d11_finalizar_volta_duas_vezes_da_400(fluxo):
    _preparar_volta(fluxo)
    assert fluxo.finalizar("volta", 1040).status_code == 200
    assert fluxo.finalizar("volta", 1040).status_code == 400


# ---------------------------------------------------------------------------------------------------------------------
# A2 / nosniff
# ---------------------------------------------------------------------------------------------------------------------
def _importar_config(**env):
    ambiente = {k: v for k, v in os.environ.items() if k not in ("ENV", "SECRET_KEY", "CORS_ORIGINS",
                                                                 "AUTO_CREATE_TABLES")}
    ambiente.update(env)
    return subprocess.run([sys.executable, "-c", "import app.core.config"], cwd=BACKEND_DIR, env=ambiente,
                          capture_output=True, text=True, timeout=60)


def test_a2_producao_exige_secret_key_com_32_caracteres():
    r = _importar_config(ENV="production", SECRET_KEY="curta", CORS_ORIGINS="https://painel.exemplo.com")
    assert r.returncode != 0 and "32" in r.stderr
    r = _importar_config(ENV="production", SECRET_KEY="x" * 32, CORS_ORIGINS="https://painel.exemplo.com")
    assert r.returncode == 0, r.stderr


def test_a2_em_dev_chave_curta_apenas_avisa():
    r = _importar_config(ENV="development", SECRET_KEY="curta")
    assert r.returncode == 0, r.stderr
    assert "menos de 32" in r.stderr


def test_static_responde_com_nosniff_e_a_api_nao_e_afetada(client):
    r = client.get("/static/uploads/nao-existe.png")
    assert r.status_code == 404
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert "x-content-type-options" not in client.get("/").headers
