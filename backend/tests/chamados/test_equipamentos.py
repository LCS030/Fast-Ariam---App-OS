"""
Regra de equipamento da OS (v0.5): catálogo de modelos, vínculo modelo + série, travas de foto de defeito e de conserto,
edição do admin e correção pós-finalização com recálculo de custo.

Cobre T-37 a T-59 do SDD (11.1) / CA-25 a CA-37 do PRD. ATENÇÃO: roda no SQLite temporário; unicidade sem diferenciar
maiúsculas em índice funcional, FK/RESTRICT, concorrência e triggers precisam ser verificados em PostgreSQL.
"""
from datetime import date
from decimal import Decimal

from app.models.chamado import OrdemServico
from app.models.configuracao_custo import ConfiguracaoCusto
from app.models.custo_os import CustoOS
from app.models.equipamento_modelo import EquipamentoModelo
from app.models.log_acao import LogAcao
from app.models.os_equipamento import OsEquipamento
from app.models.servico_equipamento import ServicoEquipamento
from app.models.visita import Visita
from app.schemas.base_schemas import StatusChamado
from app.services.tempo import hoje_negocio
from chamados.helpers import CPF_VALIDO_DIGITOS, Fluxo, criar_usuario, futuro, imagem


# --- atalhos -----------------------------------------------------------------------------------------------------------
def _eq(fluxo, mid, serie):
    return {"id_equipamento_modelo": mid, "numero_serie": serie}


def _logs(db, acao):
    db.expire_all()
    return db.query(LogAcao).filter(LogAcao.acao == acao).all()


def _vinculo(fluxo, corpo, headers=None, metodo="post", sufixo=""):
    return getattr(fluxo.c, metodo)(f"/api/chamados/{fluxo.os_id}/equipamentos{sufixo}", json=corpo,
                                    headers=headers or fluxo.admin.headers)


def _os_finalizada(fluxo, materiais=None):
    """OS de 1 equipamento levada até Finalizado; devolve o id do serviço."""
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa(1000, 1020)
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento().status_code == 200
    r = fluxo.servico(materiais=materiais or [{"nome": "Compressor", "quantidade": 1, "valor": 850.0}])
    assert r.status_code == 200, r.text
    servico_id = r.json()["id_servico"]
    assert fluxo.finalizar_atendimento().status_code == 200
    assert fluxo.volta_completa(1020, 1040).status_code == 200
    assert fluxo.os()["status"] == "Finalizado"
    return servico_id


# =====================================================================================================================
# Catálogo (T-37 a T-39)
# =====================================================================================================================
def test_t37_catalogo_so_o_admin_cria_edita_e_le(fluxo):
    r = fluxo.c.post("/api/equipamentos/", json={"modelo": "Freezer vertical modelo X"}, headers=fluxo.admin.headers)
    assert r.status_code == 201 and r.json()["is_active"] is True
    mid = r.json()["id_equipamento_modelo"]
    assert fluxo.c.post("/api/equipamentos/", json={"modelo": "Y"}, headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.post("/api/equipamentos/", json={"modelo": "   "}, headers=fluxo.admin.headers).status_code == 422
    assert fluxo.c.post("/api/equipamentos/", json={}, headers=fluxo.admin.headers).status_code == 422
    assert fluxo.c.get("/api/equipamentos/", headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.get(f"/api/equipamentos/{mid}", headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.patch(f"/api/equipamentos/{mid}", json={"modelo": "Z"}, headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.delete(f"/api/equipamentos/{mid}", headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.get(f"/api/equipamentos/{mid}", headers=fluxo.admin.headers).json()["modelo"] == \
        "Freezer vertical modelo X"
    assert fluxo.c.get("/api/equipamentos/9999", headers=fluxo.admin.headers).status_code == 404


def test_t38_modelo_duplicado_ignora_maiusculas_e_espacos(fluxo):
    assert fluxo.c.post("/api/equipamentos/", json={"modelo": "Freezer Horizontal Modelo X"},
                        headers=fluxo.admin.headers).status_code == 201
    for repetido in ("freezer horizontal modelo x", "  FREEZER HORIZONTAL MODELO X  "):
        r = fluxo.c.post("/api/equipamentos/", json={"modelo": repetido}, headers=fluxo.admin.headers)
        assert r.status_code == 409, repetido
    outro = fluxo.c.post("/api/equipamentos/", json={"modelo": "Freezer horizontal modelo Y"},
                         headers=fluxo.admin.headers).json()["id_equipamento_modelo"]
    r = fluxo.c.patch(f"/api/equipamentos/{outro}", json={"modelo": "freezer horizontal modelo x"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 409
    # renomear para um nome livre funciona (reescreve o histórico exibido, PR-45)
    r = fluxo.c.patch(f"/api/equipamentos/{outro}", json={"modelo": "Freezer horizontal modelo Z"},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["modelo"] == "Freezer horizontal modelo Z"


def test_t39_desativar_modelo_em_uso_preserva_o_historico_e_bloqueia_novos_vinculos(fluxo, db):
    os_ = fluxo.criar_os()
    mid = os_["equipamentos"][0]["id_equipamento_modelo"]
    assert fluxo.c.delete(f"/api/equipamentos/{mid}", headers=fluxo.admin.headers).status_code == 204
    # a OS existente mantém o vínculo e o nome do modelo
    assert fluxo.os()["equipamentos"][0]["modelo"].startswith("Freezer")
    assert db.query(EquipamentoModelo).count() == 1  # nunca é excluído
    # novos vínculos com modelo inativo: 422 na criação e no sub-recurso
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x",
                           "equipamentos": [_eq(fluxo, mid, "NOVO-1")]})
    assert r.status_code == 422
    assert _vinculo(fluxo, _eq(fluxo, mid, "NOVO-2")).status_code == 422
    # reativar volta a permitir
    assert fluxo.c.patch(f"/api/equipamentos/{mid}", json={"is_active": True},
                         headers=fluxo.admin.headers).status_code == 200
    assert _vinculo(fluxo, _eq(fluxo, mid, "NOVO-2")).status_code == 201
    acoes = {l.acao for l in db.query(LogAcao).all()}
    assert {"EQUIPAMENTO_MODELO_DESATIVADO", "EQUIPAMENTO_MODELO_ATUALIZADO", "OS_EQUIPAMENTO_VINCULADO"} <= acoes


# =====================================================================================================================
# OS sempre com equipamento (T-40 a T-42, T-59)
# =====================================================================================================================
def test_t40_os_sem_equipamento_nao_e_criada(fluxo, db):
    mid = fluxo.criar_modelo()
    base = {"id_cliente": fluxo.cliente_id, "descricao_cliente": "x", "id_tecnico_atribuido": fluxo.tecnico.id}
    for corpo in (base, {**base, "equipamentos": []}):
        r = fluxo.c.post("/api/chamados/", json=corpo, headers=fluxo.admin.headers)
        assert r.status_code == 422, r.text
    r = fluxo.c.post("/api/chamados/", json={**base, "equipamentos": [_eq(fluxo, 9999, "S-1")]},
                     headers=fluxo.admin.headers)
    assert r.status_code == 422
    r = fluxo.c.post("/api/chamados/", json={**base, "equipamentos": [_eq(fluxo, mid, "  ")]},
                     headers=fluxo.admin.headers)
    assert r.status_code == 422
    # nada foi criado: nem OS, nem visita, nem vínculo
    db.expire_all()
    assert db.query(OrdemServico).count() == 0 and db.query(Visita).count() == 0
    assert db.query(OsEquipamento).count() == 0


def test_t41_varios_equipamentos_na_mesma_os_e_um_servico_por_equipamento(fluxo):
    mid = fluxo.criar_modelo()
    outro = fluxo.criar_modelo()
    os_ = fluxo.criar_os(equipamentos=[_eq(fluxo, mid, "A-1"), _eq(fluxo, mid, "A-2"), _eq(fluxo, outro, "B-1")])
    assert [e["numero_serie"] for e in os_["equipamentos"]] == ["A-1", "A-2", "B-1"]
    fluxo.criar_visita()
    servicos = fluxo.servicos()
    assert len(servicos) == 3
    assert sorted(s["numero_serie"] for s in servicos) == ["A-1", "A-2", "B-1"]
    assert all(s["is_legado"] is False and s["conserto_salvo_em"] is None for s in servicos)


def test_t42_serie_duplicada_na_mesma_os_e_recusada_e_em_outra_os_e_aceita(fluxo, db):
    mid = fluxo.criar_modelo()
    r = fluxo.c.post("/api/chamados/", headers=fluxo.admin.headers,
                     json={"id_cliente": fluxo.cliente_id, "descricao_cliente": "x",
                           "equipamentos": [_eq(fluxo, mid, "ab-1"), _eq(fluxo, mid, "AB-1")]})
    assert r.status_code == 422
    assert db.query(OrdemServico).count() == 0
    fluxo.criar_os(equipamentos=[_eq(fluxo, mid, "AB-1")])
    for repetida in ("AB-1", "ab-1", "  Ab-1 "):
        assert _vinculo(fluxo, _eq(fluxo, mid, repetida)).status_code == 409, repetida
    assert len(fluxo.os()["equipamentos"]) == 1
    # a mesma série em OUTRA OS é aceita
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.criar_os(equipamentos=[_eq(fluxo, mid, "AB-1")])


def test_t59_os_legada_sem_equipamento_nao_atribui_nem_reagenda_nem_inicia(fluxo, db):
    """RN-46 / TR-15: OS anterior à v0.5 (sem equipamento) fica bloqueada até o admin vincular um equipamento."""
    pend = OrdemServico(id_cliente=fluxo.cliente_id, status=StatusChamado.PENDENTE, data_abertura=hoje_negocio(),
                        descricao_cliente="legada", is_cancelled=False)
    agend = OrdemServico(id_cliente=fluxo.cliente_id, id_tecnico_atribuido=fluxo.tecnico.id,
                         status=StatusChamado.AGENDADO, data_abertura=hoje_negocio(), descricao_cliente="legada",
                         is_cancelled=False)
    db.add_all([pend, agend])
    db.commit()
    # atribuir técnico a OS Pendente sem equipamento
    r = fluxo.c.patch(f"/api/chamados/{pend.id_os}", json={"id_tecnico_atribuido": fluxo.tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 409 and "sem equipamento" in r.json()["detail"]
    # reagendar OS Agendado sem equipamento
    r = fluxo.c.post(f"/api/chamados/{agend.id_os}/reagendar", json={"data_visita": futuro(3)},
                     headers=fluxo.admin.headers)
    assert r.status_code == 409 and "sem equipamento" in r.json()["detail"]
    # vincular um equipamento libera as operações
    mid = fluxo.criar_modelo()
    fluxo.os_id = pend.id_os
    assert _vinculo(fluxo, _eq(fluxo, mid, "LEG-1")).status_code == 201
    r = fluxo.c.patch(f"/api/chamados/{pend.id_os}", json={"id_tecnico_atribuido": fluxo.tecnico.id},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["status"] == "Agendado"
    # a visita aberta já nasce com o registro de serviço do equipamento recém-vinculado
    fluxo.criar_visita()
    assert len(fluxo.servicos()) == 1


# =====================================================================================================================
# Técnico não edita equipamento (T-43, T-44)
# =====================================================================================================================
def test_t43_tecnico_nao_cria_edita_nem_remove_equipamento_ou_serie(fluxo):
    fluxo.criar_os(n_equipamentos=2)
    fluxo.criar_visita()
    eq = fluxo.os()["equipamentos"][0]
    mid = eq["id_equipamento_modelo"]
    ids = f"/api/chamados/{fluxo.os_id}/equipamentos"
    assert _vinculo(fluxo, _eq(fluxo, mid, "TEC-1"), headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.patch(f"{ids}/{eq['id_os_equipamento']}", json={"numero_serie": "X"},
                         headers=fluxo.tecnico.headers).status_code == 403
    assert fluxo.c.delete(f"{ids}/{eq['id_os_equipamento']}", headers=fluxo.tecnico.headers).status_code == 403
    # o técnico atribuído lê (somente leitura)
    r = fluxo.c.get(ids, headers=fluxo.tecnico.headers)
    assert r.status_code == 200 and len(r.json()) == 2 and set(r.json()[0]) == {
        "id_os_equipamento", "id_equipamento_modelo", "modelo", "numero_serie"}
    # série/nome/equipamento em serviço: 422 (extra=forbid) e nada muda
    sid = fluxo.servicos()[0]["id_servico"]
    for campo, valor in (("numero_serie_atendido", "HACK"), ("nome_equipamento", "Outro"),
                         ("id_os_equipamento", 999), ("numero_serie", "HACK"), ("modelo", "Outro")):
        r = fluxo.c.patch(fluxo.url(f"servicos/{sid}"), headers=fluxo.tecnico.headers, json={campo: valor})
        assert r.status_code == 422, campo
    assert fluxo.servicos()[0]["numero_serie"] == eq["numero_serie"]
    # o técnico não cria serviço: POST responde 410
    assert fluxo.post("servicos", {"numero_serie_atendido": "SN"}).status_code == 410


def test_t44_permissao_cruzada_e_servico_de_outra_visita(fluxo, outro_tecnico, cliente_id):
    fluxo.ate_em_atendimento()
    sid = fluxo.servicos()[0]["id_servico"]
    os_url = f"/api/chamados/{fluxo.os_id}"
    assert fluxo.c.get(f"{os_url}/equipamentos", headers=outro_tecnico.headers).status_code == 403
    assert fluxo.c.post(fluxo.url(f"servicos/{sid}/salvar-conserto"), json={},
                        headers=outro_tecnico.headers).status_code == 403
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, cliente_id)
    outra.criar_os()
    outra.criar_visita()
    # id_servico de OUTRA visita/OS na URL: 404
    assert outra.c.post(outra.url(f"servicos/{sid}/salvar-conserto"), json={},
                        headers=fluxo.tecnico.headers).status_code == 404
    assert outra.c.patch(outra.url(f"servicos/{sid}"), json={"defeitos_principais": ["Refrigeração"]},
                         headers=fluxo.tecnico.headers).status_code == 404
    # equipamento de OUTRA OS na URL do sub-recurso: 404
    eq_outra = outra.os()["equipamentos"][0]["id_os_equipamento"]
    assert fluxo.c.patch(f"{os_url}/equipamentos/{eq_outra}", json={"numero_serie": "Z"},
                         headers=fluxo.admin.headers).status_code in (404, 409)


# =====================================================================================================================
# Iniciar atendimento: foto do defeito de cada equipamento (T-45, T-46)
# =====================================================================================================================
def test_t45_nao_inicia_atendimento_sem_foto_de_defeito_de_cada_equipamento(fluxo):
    fluxo.criar_os(n_equipamentos=2)
    fluxo.criar_visita()
    fluxo.ida_completa()
    pendente = fluxo.servicos()[1]
    # sem nenhuma foto: 409 listando os dois
    r = fluxo.iniciar_atendimento(completar=False)
    assert r.status_code == 409 and "foto do defeito" in r.json()["detail"]
    assert all(s["numero_serie"] in r.json()["detail"] for s in fluxo.servicos())
    # foto só do primeiro (e uma foto de CONSERTO no segundo não vale como defeito): ainda 409, lista só o segundo
    assert fluxo.foto_servico("defeito", 0).status_code == 200
    r = fluxo.iniciar_atendimento(completar=False)
    assert r.status_code == 409 and pendente["numero_serie"] in r.json()["detail"]
    assert fluxo.servicos()[0]["numero_serie"] not in r.json()["detail"]
    # a OS continua Agendado e o atendimento não foi iniciado
    assert fluxo.os()["status"] == "Agendado"
    e = fluxo.estado()
    assert e["pode_iniciar_atendimento"] is False and e["pode_registrar_foto_defeito"] is True
    assert pendente["numero_serie"] in e["bloqueio_iniciar_atendimento"]
    assert [q["foto_defeito"] for q in e["equipamentos"]] == [True, False]
    # com as duas fotos, inicia
    assert fluxo.foto_servico("defeito", 1).status_code == 200
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    assert fluxo.os()["status"] == "Em Atendimento"


def test_t46_foto_de_defeito_pequena_vale_e_foto_de_conserto_nao_vale_como_defeito(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa()
    # conserto antes de iniciar o atendimento: 409 (PR-42)
    r = fluxo.foto_servico("conserto", 0)
    assert r.status_code == 409
    assert fluxo.iniciar_atendimento(completar=False).status_code == 409
    assert fluxo.foto_servico("defeito", 0, size=(40, 30)).status_code == 200  # defeito não tem resolução mínima
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200


# =====================================================================================================================
# Finalizar atendimento: conserto salvo + foto de conserto (T-47 a T-50)
# =====================================================================================================================
def _em_atendimento_com_n(fluxo, n):
    fluxo.criar_os(n_equipamentos=n)
    fluxo.criar_visita()
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200


def test_t47_t48_nao_finaliza_sem_conserto_salvo_e_foto_de_conserto_de_cada_equipamento(fluxo, db):
    _em_atendimento_com_n(fluxo, 2)

    def tentar():
        return fluxo.finalizar_atendimento(completar=False)

    # nada salvo
    r = tentar()
    assert r.status_code == 409 and "conserto" in r.json()["detail"]
    # o registro existe (criado pelo servidor), mas sem "Salvar conserto" não conta; foto de conserto sem salvar também não
    assert fluxo.foto_servico("conserto", 0).status_code == 200
    assert tentar().status_code == 409
    # primeiro equipamento completo, segundo não
    assert fluxo.servico(indice=0).status_code == 200 and fluxo.salvar_conserto(0).status_code == 200
    r = tentar()
    assert r.status_code == 409 and fluxo.servicos()[1]["numero_serie"] in r.json()["detail"]
    # segundo com conserto salvo mas sem foto: ainda 409 ("sem foto do conserto")
    assert fluxo.servico(indice=1).status_code == 200 and fluxo.salvar_conserto(1).status_code == 200
    r = tentar()
    assert r.status_code == 409 and "sem foto do conserto" in r.json()["detail"]
    # NADA foi gravado nas tentativas recusadas
    db.expire_all()
    visita = db.get(Visita, fluxo.visita_id)
    assert visita.assinatura_url is None and visita.documento_cliente is None and visita.nome_cliente_assinatura is None
    assert visita.atendimento_fim_em is None
    # estado reflete a pendência e depois libera
    e = fluxo.estado()
    assert e["pode_finalizar_atendimento"] is False and "sem foto do conserto" in e["bloqueio_finalizar_atendimento"]
    assert fluxo.foto_servico("conserto", 1).status_code == 200
    r = tentar()
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Visita, fluxo.visita_id).documento_cliente == CPF_VALIDO_DIGITOS


def test_t49_foto_de_conserto_abaixo_de_960x1280_nao_conta(fluxo):
    _em_atendimento_com_n(fluxo, 1)
    assert fluxo.servico().status_code == 200 and fluxo.salvar_conserto().status_code == 200
    assert fluxo.foto_servico("conserto", 0, size=(800, 600)).status_code == 400
    assert fluxo.finalizar_atendimento(completar=False).status_code == 409
    assert fluxo.foto_servico("conserto", 0, size=(1280, 960)).status_code == 200  # paisagem vale
    assert fluxo.finalizar_atendimento(completar=False).status_code == 200


def test_t50_salvar_conserto_exige_atendimento_defeito_principal_e_e_idempotente(fluxo, db):
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    # antes de iniciar o atendimento: 400
    assert fluxo.salvar_conserto().status_code == 400
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    # sem defeito principal: 422
    r = fluxo.salvar_conserto()
    assert r.status_code == 422 and "defeito principal" in r.json()["detail"]
    sid = fluxo.servicos()[0]["id_servico"]
    # com a OS pausada: 400
    assert fluxo.servico().status_code == 200
    assert fluxo.pausar().status_code == 200
    assert fluxo.salvar_conserto().status_code == 400
    # idempotente: repetir mantém a primeira marca (usa outra OS sem pausa)
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.ate_em_atendimento()
    assert outra.servico().status_code == 200
    primeiro = outra.salvar_conserto().json()["conserto_salvo_em"]
    assert primeiro is not None
    assert outra.salvar_conserto().json()["conserto_salvo_em"] == primeiro
    assert len(_logs(db, "CONSERTO_SALVO")) == 1  # a repetição não gera nova auditoria
    # não é possível esvaziar os defeitos principais depois de salvar
    r = outra.c.patch(outra.url(f"servicos/{outra.servicos()[0]['id_servico']}"), headers=outra.tecnico.headers,
                      json={"defeitos_principais": []})
    assert r.status_code == 422
    assert sid != outra.servicos()[0]["id_servico"]


# =====================================================================================================================
# Pausa e multi-visita (T-51, T-52)
# =====================================================================================================================
def test_t51_pausa_dispensa_conserto_e_a_volta_leva_a_aguardando_reagendamento(fluxo):
    _em_atendimento_com_n(fluxo, 2)
    assert fluxo.pausar().status_code == 200  # conserto pendente não impede pausar
    r = fluxo.finalizar_atendimento(completar=False)
    assert r.status_code == 400 and "pausada" in r.json()["detail"]  # a checagem de pausa vem antes das travas
    assert fluxo.iniciar("volta", 1020).status_code == 200
    assert fluxo.foto_deslocamento("volta", "fim").status_code == 200
    assert fluxo.finalizar("volta", 1040).status_code == 200
    assert fluxo.os()["status"] == "Aguardando Reagendamento"


def test_t52_cada_visita_exige_novamente_foto_de_defeito_e_conserto(fluxo):
    _em_atendimento_com_n(fluxo, 1)
    primeira = fluxo.visita_id
    assert fluxo.pausar().status_code == 200
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")
    assert fluxo.finalizar("volta", 1040).status_code == 200
    r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", json={"data_visita": futuro(2)},
                     headers=fluxo.admin.headers)
    assert r.status_code == 201
    fluxo.visita_id = r.json()["id_visita"]
    assert fluxo.visita_id != primeira
    # a visita nova nasce com um registro de serviço por equipamento, sem fotos
    assert len(fluxo.servicos()) == 1 and fluxo.servicos()[0]["fotos_defeito"] == []
    fluxo.ida_completa(2000, 2020)
    r = fluxo.iniciar_atendimento(completar=False)
    assert r.status_code == 409  # as fotos da visita 1 não valem para a visita 2
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200


# =====================================================================================================================
# Edição do admin (T-53, T-54)
# =====================================================================================================================
def test_t53_os_cancelada_ou_finalizada_nao_aceita_alterar_equipamento_do_admin(fluxo):
    sid = _os_finalizada(fluxo)
    eq = fluxo.os()["equipamentos"][0]
    mid = eq["id_equipamento_modelo"]
    assert _vinculo(fluxo, _eq(fluxo, mid, "NOVO-1")).status_code == 409
    assert _vinculo(fluxo, {"numero_serie": "OUTRA"}, metodo="patch", sufixo=f"/{eq['id_os_equipamento']}"
                    ).status_code == 409  # modelo/série continuam travados mesmo com a OS Finalizada
    assert fluxo.c.delete(f"/api/chamados/{fluxo.os_id}/equipamentos/{eq['id_os_equipamento']}",
                          headers=fluxo.admin.headers).status_code == 409
    # OS cancelada
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.criar_os()
    assert outra.c.post(f"/api/chamados/{outra.os_id}/cancelar", json={"motivo": "teste"},
                        headers=outra.admin.headers).status_code == 200
    r = outra.c.post(f"/api/chamados/{outra.os_id}/equipamentos", json=_eq(outra, mid, "CANC-1"),
                     headers=outra.admin.headers)
    assert r.status_code == 409
    assert sid


def test_t54_admin_edita_ate_o_inicio_do_atendimento_e_depois_nao(fluxo, db):
    mid = fluxo.criar_modelo()
    outro_mid = fluxo.criar_modelo()
    fluxo.criar_os(equipamentos=[_eq(fluxo, mid, "E-1"), _eq(fluxo, mid, "E-2")])
    fluxo.criar_visita()
    e1, e2 = fluxo.os()["equipamentos"]
    base = f"/api/chamados/{fluxo.os_id}/equipamentos"
    # corrige série e modelo antes de iniciar: aceito e auditado
    r = fluxo.c.patch(f"{base}/{e1['id_os_equipamento']}", json={"numero_serie": "E-1B",
                                                                "id_equipamento_modelo": outro_mid},
                      headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["numero_serie"] == "E-1B" and r.json()["id_equipamento_modelo"] == outro_mid
    assert fluxo.servicos()[0]["numero_serie"] == "E-1B"  # o serviço exibe a série corrigida
    assert fluxo.c.patch(f"{base}/{e1['id_os_equipamento']}", json={"numero_serie": "E-2"},
                         headers=fluxo.admin.headers).status_code == 409  # duplicada
    logs = _logs(db, "OS_EQUIPAMENTO_ALTERADO")
    assert len(logs) == 1 and logs[0].payload["antes"]["numero_serie"] == "E-1"
    # vincular novo equipamento com a visita aberta cria o registro de serviço e recalcula o estado
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.estado()["pode_iniciar_atendimento"] is True
    r = fluxo.c.post(base, json=_eq(fluxo, mid, "E-3"), headers=fluxo.admin.headers)
    assert r.status_code == 201 and len(fluxo.servicos()) == 3
    assert fluxo.estado()["pode_iniciar_atendimento"] is False  # o novo equipamento ainda não tem foto de defeito
    assert fluxo.foto_servico("defeito", 2).status_code == 200
    # remoção: equipamento com conteúdo (foto) é bloqueado; sem conteúdo é removido junto com o serviço vazio
    assert fluxo.c.delete(f"{base}/{e2['id_os_equipamento']}", headers=fluxo.admin.headers).status_code == 409
    novo = r.json()["id_os_equipamento"]
    assert fluxo.c.delete(f"{base}/{novo}", headers=fluxo.admin.headers).status_code == 409  # já tem foto de defeito
    r = fluxo.c.post(base, json=_eq(fluxo, mid, "E-4"), headers=fluxo.admin.headers)
    vazio = r.json()["id_os_equipamento"]
    assert fluxo.c.delete(f"{base}/{vazio}", headers=fluxo.admin.headers).status_code == 204
    db.expire_all()
    assert db.query(ServicoEquipamento).filter(ServicoEquipamento.id_os_equipamento == vazio).count() == 0
    # iniciado o atendimento: nenhuma edição (409)
    fluxo.fotos_defeito_todas(estrito=False)
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    assert fluxo.c.post(base, json=_eq(fluxo, mid, "E-5"), headers=fluxo.admin.headers).status_code == 409
    assert fluxo.c.patch(f"{base}/{e2['id_os_equipamento']}", json={"numero_serie": "E-2B"},
                         headers=fluxo.admin.headers).status_code == 409
    assert fluxo.c.delete(f"{base}/{novo}", headers=fluxo.admin.headers).status_code == 409


def test_t54_nao_remove_o_ultimo_equipamento(fluxo):
    fluxo.criar_os()
    eq = fluxo.os()["equipamentos"][0]
    r = fluxo.c.delete(f"/api/chamados/{fluxo.os_id}/equipamentos/{eq['id_os_equipamento']}",
                       headers=fluxo.admin.headers)
    assert r.status_code == 409 and "último" in r.json()["detail"]
    assert len(fluxo.os()["equipamentos"]) == 1


# =====================================================================================================================
# Correção administrativa de OS Finalizada + recálculo de custo (T-58)
# =====================================================================================================================
def test_t58_admin_corrige_fotos_em_os_finalizada(fluxo, db):
    sid = _os_finalizada(fluxo)
    antes = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=fluxo.admin.headers).json()
    url_servico = fluxo.url(f"servicos/{sid}")
    admin = fluxo.admin.headers

    def fotos():
        return fluxo.c.get(f"{url_servico}/fotos", headers=admin).json()

    # envia uma segunda foto de conserto (correção) e uma de defeito
    r = fluxo.c.post(f"{url_servico}/upload-foto", headers=admin, data={"tipo": "conserto"},
                     files={"file": imagem(960, 1280)})
    assert r.status_code == 200, r.text
    nova = r.json()["id_foto"]
    # conserto continua exigindo 960x1280 também na correção
    r = fluxo.c.post(f"{url_servico}/upload-foto", headers=admin, data={"tipo": "conserto"},
                     files={"file": imagem(300, 200)})
    assert r.status_code == 400
    # remove a foto antiga (agora há 2): ok; remover a última do tipo: 409
    antiga = [f for f in fotos()["fotos_conserto"] if f["id_foto"] != nova][0]["id_foto"]
    assert fluxo.c.delete(f"{url_servico}/fotos/{antiga}", headers=admin).status_code == 204
    r = fluxo.c.delete(f"{url_servico}/fotos/{nova}", headers=admin)
    assert r.status_code == 409 and "única foto" in r.json()["detail"]
    # fotos de defeito: pode remover as excedentes, nunca a última
    defeitos = [f["id_foto"] for f in fotos()["fotos_defeito"]]
    for excedente in defeitos[:-1]:
        assert fluxo.c.delete(f"{url_servico}/fotos/{excedente}", headers=admin).status_code == 204
    assert fluxo.c.delete(f"{url_servico}/fotos/{defeitos[-1]}", headers=admin).status_code == 409
    assert len(fotos()["fotos_defeito"]) == 1
    assert fluxo.c.delete(f"{url_servico}/fotos/9999", headers=admin).status_code == 404
    # auditoria da correção
    acoes = sorted((l.payload["acao"], l.payload["tipo"]) for l in _logs(db, "FOTO_CORRIGIDA_ADMIN"))
    esperado = sorted([("enviada", "conserto"), ("removida", "conserto")]
                      + [("removida", "defeito")] * (len(defeitos) - 1))
    assert acoes == esperado
    # corrigir só fotos não altera o custo nem o status
    depois = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=admin).json()
    assert depois["total_geral"] == antes["total_geral"] and fluxo.os()["status"] == "Finalizado"
    # o técnico não corrige nada após a finalização
    tec = fluxo.tecnico.headers
    assert fluxo.c.post(f"{url_servico}/upload-foto", headers=tec, data={"tipo": "defeito"},
                        files={"file": imagem(300, 200)}).status_code == 409
    assert fluxo.c.delete(f"{url_servico}/fotos/{nova}", headers=tec).status_code == 403


def test_t58_correcao_de_materiais_recalcula_o_custo_com_os_valores_congelados(fluxo, db):
    sid = _os_finalizada(fluxo, materiais=[{"nome": "Compressor", "quantidade": 1, "valor": 850.0}])
    admin = fluxo.admin.headers
    antes = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=admin).json()
    assert antes["congelado"] is True and antes["custo_total_materiais"] == 850.0
    congelados = antes["valores_utilizados"]

    # a configuração global muda DEPOIS da finalização: o recálculo NÃO pode usá-la (RN-33)
    db.add(ConfiguracaoCusto(id_configuracao=1, primeira_hora_tecnico=Decimal("999.00"),
                             hora_tecnico=Decimal("999.00"), tempo_deslocamento_tecnico=Decimal("999.00"),
                             quilometragem=Decimal("999.00")))
    db.commit()

    r = fluxo.c.patch(fluxo.url(f"servicos/{sid}"), headers=admin, json={
        "materiais_utilizados": [{"nome": "Compressor", "quantidade": 2, "valor": 850.0},
                                 {"nome": "Filtro", "quantidade": 3, "valor": 10.0}]})
    assert r.status_code == 200, r.text
    assert [m["nome"] for m in r.json()["materiais_utilizados"]] == ["Compressor", "Filtro"]

    depois = fluxo.c.get(f"/api/chamados/{fluxo.os_id}/custos", headers=admin).json()
    assert depois["congelado"] is True and depois["valores_utilizados"] == congelados  # valores inalterados
    assert depois["custo_total_materiais"] == 1730.0  # 2 x 850 + 3 x 10
    # só os materiais mudaram: km, deslocamento, serviço, pedágio e frete permanecem iguais
    for campo in ("custo_total_km", "custo_total_deslocamento", "custo_total_servico", "custo_total_pedagio",
                  "custo_total_frete"):
        assert depois[campo] == antes[campo], campo
    assert round(depois["total_geral"] - antes["total_geral"], 2) == 880.0
    snapshot = db.get(CustoOS, fluxo.os_id)
    db.refresh(snapshot)
    assert float(snapshot.total) == depois["total_geral"] and snapshot.valores_utilizados == congelados
    # auditoria com antes/depois e total anterior/novo
    (log,) = _logs(db, "MATERIAIS_CORRIGIDOS_ADMIN")
    assert log.papel == "admin" and log.payload["custo_total_anterior"] == antes["total_geral"]
    assert log.payload["custo_total_novo"] == depois["total_geral"]
    assert [m["nome"] for m in log.payload["materiais_antes"]] == ["Compressor"]
    assert [m["nome"] for m in log.payload["materiais_depois"]] == ["Compressor", "Filtro"]
    assert fluxo.os()["status"] == "Finalizado"


def test_t58_so_fotos_e_materiais_sao_editaveis_e_so_com_a_os_finalizada(fluxo):
    sid = _os_finalizada(fluxo)
    admin = fluxo.admin.headers
    url = fluxo.url(f"servicos/{sid}")
    # qualquer campo além de materiais_utilizados: 422
    for corpo in ({"defeitos_principais": ["Refrigeração"]}, {"defeito_outros_descricao": "x"},
                  {"materiais_utilizados": [], "defeitos_principais": ["Refrigeração"]}, {}):
        assert fluxo.c.patch(url, json=corpo, headers=admin).status_code == 422, corpo
    # modelo e série não mudam nem com a OS Finalizada
    eq = fluxo.os()["equipamentos"][0]
    assert fluxo.c.patch(f"/api/chamados/{fluxo.os_id}/equipamentos/{eq['id_os_equipamento']}",
                         json={"numero_serie": "X"}, headers=admin).status_code == 409
    # o técnico não corrige
    assert fluxo.c.patch(url, json={"materiais_utilizados": []}, headers=fluxo.tecnico.headers).status_code == 409
    # OS que NÃO está Finalizada: a correção do admin é recusada
    outra = Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)
    outra.ate_em_atendimento()
    osid = outra.servicos()[0]["id_servico"]
    assert outra.c.patch(outra.url(f"servicos/{osid}"), json={"materiais_utilizados": []},
                         headers=admin).status_code == 409
    assert outra.c.post(outra.url(f"servicos/{osid}/upload-foto"), headers=admin, data={"tipo": "defeito"},
                        files={"file": imagem(300, 200)}).status_code == 409
    assert outra.c.delete(outra.url(f"servicos/{osid}/fotos/1"), headers=admin).status_code == 409


# =====================================================================================================================
# Estado e auditoria
# =====================================================================================================================
def test_estado_de_visita_nao_vigente_nao_expoe_pendencias(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.pausar()
    fluxo.iniciar("volta", 1020)
    fluxo.foto_deslocamento("volta", "fim")
    fluxo.finalizar("volta", 1040)
    antiga = fluxo.visita_id
    fluxo.c.post(f"/api/chamados/{fluxo.os_id}/reagendar", json={"data_visita": futuro(3)}, headers=fluxo.admin.headers)
    fluxo.visita_id = antiga
    e = fluxo.estado()
    assert e["visita_vigente"] is False and e["equipamentos"] == []
    assert e["bloqueio_iniciar_atendimento"] is None and e["pode_registrar_foto_defeito"] is False


def test_iniciar_e_finalizar_registram_os_equipamentos_conferidos_na_auditoria(fluxo, db):
    fluxo.criar_os(n_equipamentos=2)
    fluxo.criar_visita()
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    assert fluxo.finalizar_atendimento().status_code == 200
    ids = sorted(e["id_os_equipamento"] for e in fluxo.os()["equipamentos"])
    for acao in ("ATENDIMENTO_INICIADO", "ATENDIMENTO_FINALIZADO"):
        (log,) = _logs(db, acao)
        assert sorted(log.payload["equipamentos_conferidos"]) == ids
