"""
v0.7 - cifragem dos dados pessoais restantes (SEG-22 ampliado): CA-V07-1 a CA-V07-9 e os ataques do Security.

  H1  sync_evento.payload: `documento_cliente` e `nome_cliente` cifrados POR CHAVE, AAD POR LINHA
      (`sync_evento.<chave>|<client_event_id>`), em eventos aplicados e rejeitados.
  H2  cliente.contato_principal_nome/telefone e visita.nome_cliente_assinatura como `TextoCifrado` + migracao 0014 + script.

Roda no SQLite temporario (tests/conftest.py). NAO verifica nada em PostgreSQL/Supabase: JSONB real, VARCHAR(n), a trava de
`information_schema` do script e a execucao das migracoes .sql NAO sao verificaveis aqui (ver os testes `*_limite_sqlite*`).
Dado pessoal usado aqui e sempre ficticio. Convencao: "SEGREDO" marca texto que NUNCA pode aparecer legivel no banco.
"""
import base64
import json
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, text

from app.core import config, crypto
from app.core.crypto import ErroDecifragem, TextoCifrado
from app.db.database import engine
from app.main import app
from app.models.cliente import Cliente
from app.models.sync_evento import SyncEvento
from app.models.visita import Visita
from app.services import sync_service
from app.services.sync_service import (CHAVES_PESSOAIS_PAYLOAD, cifrar_payload, contexto_payload, decifrar_payload)
from chamados.helpers import CPF_VALIDO, CPF_VALIDO_DIGITOS, Fluxo, assinatura_b64
from chamados.test_cifragem_integridade import (EVENTOS, _bruto, _carregar_script, _finalizar, _verificar,  # noqa: F401
                                                banco_legado)
from chamados.test_sync import AGORA, _arquivo, _ev, _id, _prep
from tests.test_auth_tecnicos_clientes import payload_cliente

BACKEND = Path(__file__).resolve().parents[2]
NOME_ASSINANTE = "SEGREDO José da Silva 😀"
MARCADORES = ("SEGREDO", CPF_VALIDO_DIGITOS, CPF_VALIDO)


# =====================================================================================================================
# Auxiliares
# =====================================================================================================================

def _cliente_sem_excecao() -> TestClient:
    """Cliente HTTP que devolve 500 em vez de relancar a excecao do servidor (o `client` da fixture relanca)."""
    return TestClient(app, raise_server_exceptions=False)


def _enviar_bruto(fluxo, eventos, headers=None):
    """POST /api/sync/eventos com JSON ASCII-escapado: o `json=` do httpx nao consegue serializar surrogate isolado."""
    corpo = {"dispositivo_id": "aparelho-1", "enviado_em": AGORA().isoformat(), "eventos": eventos}
    return fluxo.c.post("/api/sync/eventos", content=json.dumps(corpo),
                        headers={**(headers or fluxo.tecnico.headers), "Content-Type": "application/json"})


def _res(r):
    assert r.status_code == 200, r.text
    return r.json()["resultados"]


def _linha_sync(cid: str) -> dict:
    """Linha de sync_evento por SQL CRU (sem ORM, sem o tipo JSON do SQLAlchemy): payload e o TEXTO gravado."""
    with engine.connect() as conn:
        linha = conn.execute(text("SELECT payload, resultado, codigo, detalhe, tipo, id_os, id_visita FROM sync_evento "
                                  "WHERE client_event_id = :i"), {"i": uuid.UUID(cid).hex}).fetchone()
    assert linha is not None, f"evento {cid} nao foi gravado"
    bruto = linha[0]
    return {"payload_texto": bruto, "payload": json.loads(bruto), "resultado": linha[1], "codigo": linha[2],
            "detalhe": linha[3], "tipo": linha[4], "id_os": linha[5], "id_visita": linha[6]}


def _toda_a_tabela_sync() -> list:
    with engine.connect() as conn:
        return [tuple(r) for r in conn.execute(text("SELECT * FROM sync_evento ORDER BY client_event_id")).fetchall()]


def _esperado_cifrado(valor):
    """Texto que `cifrar_payload` deve cifrar para `valor` (None fica None)."""
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor.encode("utf-8", "backslashreplace").decode("utf-8")
    return json.dumps(valor, ensure_ascii=True, default=str)


def _conferir_payload_cifrado(cid: str, valor, chaves=CHAVES_PESSOAIS_PAYLOAD) -> dict:
    """Nada legivel no banco para `valor`; cada chave pessoal e None ou `enc1:` que decifra com a AAD DESTA linha."""
    linha = _linha_sync(cid)
    for marcador in MARCADORES:
        assert marcador not in linha["payload_texto"], f"{marcador!r} legivel no payload gravado"
    for chave in chaves:
        gravado = linha["payload"].get(chave)
        if valor is None:
            assert gravado is None
            continue
        assert crypto.esta_cifrado(gravado), f"{chave} nao cifrado: {gravado!r}"
        assert crypto.decifrar(gravado, contexto_payload(chave, cid)) == _esperado_cifrado(valor)
    return linha


def _novo_fluxo(fluxo) -> Fluxo:
    return Fluxo(fluxo.c, fluxo.admin, fluxo.tecnico, fluxo.cliente_id)


def _pronto_para_finalizar(fluxo) -> None:
    """OS/visita em atendimento com conserto completo (so falta a assinatura)."""
    fluxo.criar_os()
    fluxo.criar_visita()
    fluxo.ida_completa()
    fluxo.fotos_defeito_todas()
    assert fluxo.iniciar_atendimento(completar=False).status_code == 200
    fluxo.conserto_completo(estrito=True)


def _finalizar_com(fluxo, nome: str) -> None:
    fluxo.ate_em_atendimento()
    r = fluxo.finalizar_atendimento(cpf=CPF_VALIDO, nome=nome)
    assert r.status_code == 200, r.text


# =====================================================================================================================
# H1 - CA-V07-1: evento aplicado
# =====================================================================================================================

def test_ca_v07_1_finalizar_atendimento_por_sync_grava_payload_cifrado_e_o_handler_recebe_o_original(fluxo, db):
    _pronto_para_finalizar(fluxo)
    f_ass, r = _arquivo(fluxo, "assinatura")
    assert r.status_code == 200, r.text
    ev = _ev(fluxo, "atendimento_finalizado", {"nome_cliente": NOME_ASSINANTE, "documento_cliente": CPF_VALIDO,
                                               "assinatura_ref": f_ass}, AGORA())
    res = _res(_enviar_bruto(fluxo, [ev]))
    assert [(x["resultado"], x["codigo"]) for x in res] == [("aplicado", None)], res
    cid = ev["client_event_id"]

    linha = _linha_sync(cid)
    assert linha["resultado"] == "aplicado"
    assert linha["payload"]["nome_cliente"].startswith("enc1:") and linha["payload"]["documento_cliente"].startswith("enc1:")
    for marcador in MARCADORES:
        assert marcador not in linha["payload_texto"]
    assert linha["payload"]["assinatura_ref"] == f_ass  # chaves nao pessoais seguem em claro
    assert crypto.decifrar(linha["payload"]["nome_cliente"], contexto_payload("nome_cliente", cid)) == NOME_ASSINANTE
    assert crypto.decifrar(linha["payload"]["documento_cliente"], contexto_payload("documento_cliente", cid)) == CPF_VALIDO

    # o handler recebeu os valores ORIGINAIS: a visita ficou com CPF (so digitos) e nome corretos (API em claro)...
    visita = fluxo.os()["visitas"][0]
    assert visita["documento_cliente"] == CPF_VALIDO_DIGITOS and visita["nome_cliente_assinatura"] == NOME_ASSINANTE
    # ...e cifrados na propria visita (SQL cru)
    nome_bruto, doc_bruto = _bruto("SELECT nome_cliente_assinatura, documento_cliente FROM visita WHERE id_visita=:i",
                                   i=fluxo.visita_id)[0]
    assert nome_bruto.startswith("enc1:") and doc_bruto.startswith("enc1:")
    assert "SEGREDO" not in nome_bruto and CPF_VALIDO_DIGITOS not in doc_bruto
    db.expire_all()
    assert db.get(Visita, fluxo.visita_id).nome_cliente_assinatura == NOME_ASSINANTE
    assert _verificar(fluxo).json()["estado"] == "integro"  # selo continua valido (calculado sobre o claro)


def test_finalizar_atendimento_online_grava_nome_da_assinatura_cifrado_e_a_api_devolve_em_claro(fluxo, db):
    _finalizar_com(fluxo, NOME_ASSINANTE)
    bruto = _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0][0]
    assert bruto.startswith("enc1:") and "SEGREDO" not in bruto
    assert crypto.decifrar(bruto, "visita.nome_cliente_assinatura") == NOME_ASSINANTE
    assert fluxo.os()["visitas"][0]["nome_cliente_assinatura"] == NOME_ASSINANTE
    # AAD por COLUNA: o nome nao decifra com o contexto do CPF (e vice-versa)
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(bruto, "visita.documento_cliente")


def test_ev_chave_pessoal_em_evento_de_outro_tipo_tambem_e_cifrada(fluxo):
    """A cifragem e POR CHAVE, nao por tipo de evento: nome/CPF em deslocamento_ida_iniciado (extra ignorado pelo handler)."""
    _prep(fluxo)
    ev = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 10, "nome_cliente": NOME_ASSINANTE,
                                                  "documento_cliente": CPF_VALIDO}, AGORA() - timedelta(minutes=2))
    res = _res(_enviar_bruto(fluxo, [ev]))
    assert res[0]["resultado"] == "aplicado"
    linha = _conferir_payload_cifrado(ev["client_event_id"], NOME_ASSINANTE, chaves=("nome_cliente",))
    assert crypto.esta_cifrado(linha["payload"]["documento_cliente"]) and linha["payload"]["km_inicio"] == 10


def test_ocorrido_em_original_e_demais_chaves_do_payload_ficam_em_claro(fluxo):
    fluxo.criar_os()
    fluxo.criar_visita()
    relogio = AGORA() - timedelta(hours=3)  # aparelho atrasado: o servidor corrige ocorrido_em e guarda o original
    ev = _ev(fluxo, "deslocamento_ida_iniciado", {"km_inicio": 5, "nome_cliente": NOME_ASSINANTE}, relogio - timedelta(minutes=10))
    corpo = {"dispositivo_id": "d", "enviado_em": relogio.isoformat(), "eventos": [ev]}
    r = fluxo.c.post("/api/sync/eventos", content=json.dumps(corpo),
                     headers={**fluxo.tecnico.headers, "Content-Type": "application/json"})
    assert _res(r)[0]["resultado"] == "aplicado"
    payload = _linha_sync(ev["client_event_id"])["payload"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT.*", payload["ocorrido_em_original"]) and payload["km_inicio"] == 5
    assert payload["nome_cliente"].startswith("enc1:")


# =====================================================================================================================
# H1 - CA-V07-2 e CA-V07-3: rejeitados e valores de qualquer tipo (matriz valor x cenario)
# =====================================================================================================================

VALORES = {
    "none": None,
    "vazio": "",
    "int": 52998224725,
    "bool": True,
    "float": 52998224.725,
    "dict": {"cpf": "52998224725", "nome": "SEGREDO"},
    "lista": ["52998224725", "SEGREDO"],
    "longo": "SEGREDO" + "x" * 5000,
    "acentos_emoji": "SEGREDO José Ç 😀",
    "surrogate_isolado": "SEGREDO\ud800fim",
    "nul": "SEGREDO\x00fim",
}
CENARIOS = ("cancelada", "reatribuida", "tipo_desconhecido", "dependencia_rejeitada", "validacao")
CODIGO_ESPERADO = {"cancelada": "OS_CANCELADA", "reatribuida": "OS_REATRIBUIDA", "tipo_desconhecido": "VALIDACAO",
                   "dependencia_rejeitada": "DEPENDENCIA_REJEITADA", "validacao": "VALIDACAO"}


def _enviar_cenario(fluxo, outro_tecnico, cenario: str, valor):
    """Envia 1 lote que cai no `cenario` de rejeicao; devolve o client_event_id do evento que carrega o `valor`."""
    _prep(fluxo)
    payload = {"nome_cliente": valor, "documento_cliente": valor}
    quando = AGORA() - timedelta(minutes=1)
    if cenario == "cancelada":
        r = fluxo.c.post(f"/api/chamados/{fluxo.os_id}/cancelar", json={"motivo": "teste"}, headers=fluxo.admin.headers)
        assert r.status_code == 200, r.text
    elif cenario == "reatribuida":
        r = fluxo.c.patch(f"/api/chamados/{fluxo.os_id}", json={"id_tecnico_atribuido": outro_tecnico.id},
                          headers=fluxo.admin.headers)
        assert r.status_code == 200, r.text
    if cenario == "tipo_desconhecido":
        eventos = [_ev(fluxo, "tipo_que_nao_existe", payload, quando)]
    elif cenario == "dependencia_rejeitada":  # 1o evento rejeitado bloqueia o seguinte da mesma visita (sem handler)
        eventos = [_ev(fluxo, "tipo_que_nao_existe", {}, quando - timedelta(minutes=1)),
                   _ev(fluxo, "atendimento_finalizado", payload, quando)]
    else:  # cancelada / reatribuida / validacao (sem assinatura_ref: ValidationError antes de qualquer arquivo)
        eventos = [_ev(fluxo, "atendimento_finalizado", payload, quando)]
    r = _enviar_bruto(fluxo, eventos)
    assert r.status_code == 200, r.text  # nunca 500 por causa do formato do valor
    resultados = r.json()["resultados"]
    alvo = eventos[-1]["client_event_id"]
    resultado = next(x for x in resultados if x["client_event_id"] == alvo)
    return alvo, resultado, r.text


@pytest.mark.parametrize("cenario", CENARIOS)
@pytest.mark.parametrize("nome_valor", list(VALORES))
def test_ca_v07_2_e_3_evento_rejeitado_grava_o_registro_sem_nada_legivel(fluxo, outro_tecnico, cenario, nome_valor):
    valor = VALORES[nome_valor]
    cid, resultado, corpo_resposta = _enviar_cenario(fluxo, outro_tecnico, cenario, valor)
    assert resultado["resultado"] == "rejeitado" and resultado["codigo"] == CODIGO_ESPERADO[cenario], resultado
    linha = _conferir_payload_cifrado(cid, valor)
    assert linha["resultado"] == "rejeitado" and linha["codigo"] == CODIGO_ESPERADO[cenario]
    # nem a resposta HTTP nem `detalhe` ecoam o dado pessoal
    for marcador in ("SEGREDO", CPF_VALIDO_DIGITOS):
        assert marcador not in corpo_resposta and marcador not in (linha["detalhe"] or "")


def test_ca_v07_3_none_nao_vira_enc1_e_valor_nao_string_vira_texto_json_cifrado(fluxo, outro_tecnico):
    """Contrato explicito: None fica None; int/bool/float/dict/lista viram TEXTO JSON cifrado (round-trip exato so p/ str)."""
    cid, _, _ = _enviar_cenario(fluxo, outro_tecnico, "tipo_desconhecido", {"a": [1, True, None]})
    gravado = _linha_sync(cid)["payload"]["nome_cliente"]
    assert crypto.decifrar(gravado, contexto_payload("nome_cliente", cid)) == '{"a": [1, true, null]}'
    assert _esperado_cifrado(True) == "true" and _esperado_cifrado(1.5) == "1.5"


def test_ca_v07_3_chave_ausente_continua_ausente(fluxo):
    _prep(fluxo)
    ev = _ev(fluxo, "tipo_que_nao_existe", {"km_inicio": 3}, AGORA() - timedelta(minutes=1))
    assert _res(_enviar_bruto(fluxo, [ev]))[0]["codigo"] == "VALIDACAO"
    payload = _linha_sync(ev["client_event_id"])["payload"]
    assert "nome_cliente" not in payload and "documento_cliente" not in payload and payload["km_inicio"] == 3


def test_lote_misto_sem_nenhuma_linha_legivel_conferido_por_sql_cru(fluxo, outro_tecnico):
    """Um unico lote com aplicado + 4 rejeicoes diferentes (OS distintas); nenhuma linha da tabela pode ter dado legivel."""
    f_ok, f_canc, f_reat, f_dep = fluxo, _novo_fluxo(fluxo), _novo_fluxo(fluxo), _novo_fluxo(fluxo)
    _pronto_para_finalizar(f_ok)
    f_ass, _ = _arquivo(f_ok, "assinatura")
    for f in (f_canc, f_reat, f_dep):
        f.criar_os()
        f.criar_visita()
    assert f_canc.c.post(f"/api/chamados/{f_canc.os_id}/cancelar", json={"motivo": "x"},
                         headers=f_canc.admin.headers).status_code == 200
    assert f_reat.c.patch(f"/api/chamados/{f_reat.os_id}", json={"id_tecnico_atribuido": outro_tecnico.id},
                          headers=f_reat.admin.headers).status_code == 200
    q = AGORA()
    pessoal = {"nome_cliente": NOME_ASSINANTE, "documento_cliente": CPF_VALIDO}
    eventos = [
        _ev(f_ok, "atendimento_finalizado", {**pessoal, "assinatura_ref": f_ass}, q),
        _ev(f_canc, "atendimento_finalizado", pessoal, q),
        _ev(f_reat, "atendimento_finalizado", pessoal, q),
        _ev(f_dep, "tipo_que_nao_existe", pessoal, q),
        _ev(f_dep, "atendimento_finalizado", pessoal, q + timedelta(seconds=1)),
        _ev(f_ok, "deslocamento_volta_iniciado", {"km_inicio": 1, "nome_cliente": 52998224725}, q + timedelta(minutes=1)),
    ]
    resp = _enviar_bruto(f_ok, eventos)
    assert resp.status_code == 200, resp.text
    codigos = [(x["resultado"], x["codigo"]) for x in resp.json()["resultados"]]
    assert codigos == [("aplicado", None), ("rejeitado", "OS_CANCELADA"), ("rejeitado", "OS_REATRIBUIDA"),
                       ("rejeitado", "VALIDACAO"), ("rejeitado", "DEPENDENCIA_REJEITADA"), ("aplicado", None)]
    with engine.connect() as conn:
        linhas = conn.execute(text("SELECT client_event_id, payload, detalhe FROM sync_evento")).fetchall()
    assert len(linhas) == 6
    for _id_, payload_texto, detalhe in linhas:
        for marcador in ("SEGREDO", CPF_VALIDO_DIGITOS, CPF_VALIDO, "José"):
            assert marcador not in payload_texto and marcador not in (detalhe or "")
        payload = json.loads(payload_texto)
        for chave in CHAVES_PESSOAIS_PAYLOAD:
            assert payload.get(chave) is None or payload[chave].startswith("enc1:")
    # sentinela: o proprio SQL cru enxerga o claro quando ele existe (o teste nao esta cego)
    assert "52998224725" in _bruto("SELECT 'x52998224725x'")[0][0]


# =====================================================================================================================
# H1 - CA-V07-4: reenvio
# =====================================================================================================================

@pytest.mark.parametrize("cenario", ["aplicado", "rejeitado"])
def test_ca_v07_4_reenvio_do_mesmo_client_event_id_e_duplicado_e_nao_muda_o_registro_byte_a_byte(fluxo, cenario):
    if cenario == "aplicado":
        _pronto_para_finalizar(fluxo)
        f_ass, _ = _arquivo(fluxo, "assinatura")
        ev = _ev(fluxo, "atendimento_finalizado", {"nome_cliente": NOME_ASSINANTE, "documento_cliente": CPF_VALIDO,
                                                   "assinatura_ref": f_ass}, AGORA())
    else:
        _prep(fluxo)
        ev = _ev(fluxo, "tipo_que_nao_existe", {"nome_cliente": NOME_ASSINANTE, "documento_cliente": CPF_VALIDO},
                 AGORA() - timedelta(minutes=1))
    primeira = _res(_enviar_bruto(fluxo, [ev]))[0]
    assert primeira["resultado"] == cenario
    antes = _toda_a_tabela_sync()
    segunda = _res(_enviar_bruto(fluxo, [ev]))[0]
    assert segunda["resultado"] == "duplicado" and segunda["client_event_id"] == ev["client_event_id"]
    assert _toda_a_tabela_sync() == antes  # SELECT * identico: nenhum byte (nem nonce) mudou
    # reenvio com payload DIFERENTE para o mesmo id: continua duplicado e o gravado nao e sobrescrito
    outro = {**ev, "payload": {**ev["payload"], "nome_cliente": "OUTRO SEGREDO"}}
    assert _res(_enviar_bruto(fluxo, [outro]))[0]["resultado"] == "duplicado"
    assert _toda_a_tabela_sync() == antes


# =====================================================================================================================
# H1 - valor ja com prefixo enc1:, adulteracao, troca entre eventos e entre chaves (AAD por linha)
# =====================================================================================================================

def test_valor_enc1_enviado_pelo_cliente_e_cifrado_por_cima_e_nunca_tratado_como_ja_protegido(fluxo):
    _prep(fluxo)
    forjado_curto = "enc1:AAAA"
    # um enc1: VALIDO (do mesmo CPF, outro contexto) que o aparelho "ja cifrou": o servidor nao pode confiar nisso
    valido_outro_ctx = crypto.cifrar(CPF_VALIDO, "visita.documento_cliente")
    ev = _ev(fluxo, "tipo_que_nao_existe", {"nome_cliente": forjado_curto, "documento_cliente": valido_outro_ctx},
             AGORA() - timedelta(minutes=1))
    assert _res(_enviar_bruto(fluxo, [ev]))[0]["codigo"] == "VALIDACAO"
    cid = ev["client_event_id"]
    payload = _linha_sync(cid)["payload"]
    assert payload["nome_cliente"] != forjado_curto and payload["documento_cliente"] != valido_outro_ctx
    # o que foi gravado e o enc1: ENVIADO, cifrado de novo com a AAD da linha (decifra para o texto enviado)
    assert crypto.decifrar(payload["nome_cliente"], contexto_payload("nome_cliente", cid)) == forjado_curto
    assert crypto.decifrar(payload["documento_cliente"], contexto_payload("documento_cliente", cid)) == valido_outro_ctx
    # e sem a AAD da linha o valor gravado nao abre (nao ha "texto do cliente tratado como cifra do servidor")
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(payload["documento_cliente"], "visita.documento_cliente")


def _dois_eventos_rejeitados(fluxo):
    _prep(fluxo)
    q = AGORA() - timedelta(minutes=1)
    a = _ev(fluxo, "tipo_que_nao_existe", {"nome_cliente": "SEGREDO A", "documento_cliente": "SEGREDO-DOC-A"}, q)
    f2 = _novo_fluxo(fluxo)
    f2.criar_os()
    f2.criar_visita()
    b = _ev(f2, "tipo_que_nao_existe", {"nome_cliente": "SEGREDO B", "documento_cliente": "SEGREDO-DOC-B"}, q)
    assert all(x["codigo"] == "VALIDACAO" for x in _res(_enviar_bruto(fluxo, [a, b])))
    return a["client_event_id"], b["client_event_id"]


def test_aad_por_linha_valor_trocado_entre_eventos_e_entre_chaves_nao_decifra(fluxo):
    a, b = _dois_eventos_rejeitados(fluxo)
    pa, pb = _linha_sync(a)["payload"], _linha_sync(b)["payload"]
    # sanidade: cada um decifra na propria linha
    assert crypto.decifrar(pa["nome_cliente"], contexto_payload("nome_cliente", a)) == "SEGREDO A"
    assert crypto.decifrar(pb["nome_cliente"], contexto_payload("nome_cliente", b)) == "SEGREDO B"
    # troca ENTRE EVENTOS (mesma chave): falha - era o limite herdado do AAD por coluna, fechado pela AAD por linha
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(pb["nome_cliente"], contexto_payload("nome_cliente", a))
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(pa["documento_cliente"], contexto_payload("documento_cliente", b))
    # troca ENTRE CHAVES (mesma linha)
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(pa["nome_cliente"], contexto_payload("documento_cliente", a))
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(pa["documento_cliente"], contexto_payload("nome_cliente", a))
    # a AAD antiga (por coluna, sem id) tambem nao abre o valor novo
    with pytest.raises(ErroDecifragem):
        crypto.decifrar(pa["nome_cliente"], "sync_evento.nome_cliente")
    assert contexto_payload("nome_cliente", a) == f"sync_evento.nome_cliente|{a}"


def test_aad_por_linha_adulterar_um_byte_do_enc1_falha(fluxo):
    a, _ = _dois_eventos_rejeitados(fluxo)
    valor = _linha_sync(a)["payload"]["nome_cliente"]
    bruto = bytearray(base64.b64decode(valor[len("enc1:"):]))
    for posicao in (0, 12, len(bruto) - 1):  # nonce, ciphertext e tag
        mutado = bytearray(bruto)
        mutado[posicao] ^= 0x01
        with pytest.raises(ErroDecifragem):
            crypto.decifrar("enc1:" + base64.b64encode(bytes(mutado)).decode(), contexto_payload("nome_cliente", a))


def test_script_detecta_como_anomalia_valor_trocado_entre_eventos_por_sql_cru(fluxo):
    """O --verificar nao 'aceita' enc1: so pelo prefixo: valor de outra linha e ANOMALIA (reportada por ID)."""
    a, b = _dois_eventos_rejeitados(fluxo)
    pa, pb = _linha_sync(a)["payload"], _linha_sync(b)["payload"]
    with engine.begin() as conn:  # alguem troca o nome cifrado dos dois eventos direto no banco
        for cid, novo in ((a, pb["nome_cliente"]), (b, pa["nome_cliente"])):
            payload = {**_linha_sync(cid)["payload"], "nome_cliente": novo}
            conn.execute(text("UPDATE sync_evento SET payload=:p WHERE client_event_id=:i"),
                         {"p": json.dumps(payload), "i": uuid.UUID(cid).hex})
    mod = _carregar_script()
    contagens, ids = mod.verificar_payload_sync(engine)
    assert contagens["sync_evento.payload_anomalo"] == 2 and sorted(ids) == sorted([a, b])
    assert contagens["sync_evento.payload.nome_cliente"] == 0  # nao e "legivel": e anomalo


# =====================================================================================================================
# H1 - unidades de cifrar_payload / decifrar_payload
# =====================================================================================================================

def test_cifrar_payload_trabalha_em_copia_e_nunca_lanca_excecao_por_causa_do_valor():
    cid = uuid.uuid4()

    class _Hostil:
        def __str__(self):
            raise RuntimeError("nao serializa")

    fundo = x = {}
    for _ in range(5000):  # aninhamento que estoura o json.dumps (RecursionError)
        x["a"] = {}
        x = x["a"]
    for valor in (None, "", "a", 0, 1.5, float("nan"), float("inf"), True, [], {}, [1, {"a": 2}], "x" * 100000,
                  "\ud800", "\x00", "a\udfffb", 10 ** 400, _Hostil(), fundo, b"bytes", {1, 2}):
        original = {"nome_cliente": valor, "documento_cliente": valor, "km_inicio": 5}
        copia = cifrar_payload(original, cid)  # nao pode lancar
        assert original["nome_cliente"] is valor, "o original em memoria (Ctx.payload) nao pode ser alterado"
        assert copia is not original and copia["km_inicio"] == 5
        if valor is None:
            assert copia["nome_cliente"] is None
        else:
            assert crypto.esta_cifrado(copia["nome_cliente"]) and crypto.esta_cifrado(copia["documento_cliente"])
            crypto.decifrar(copia["nome_cliente"], contexto_payload("nome_cliente", cid))  # decifra sem lancar
    # marcador fixo quando nem o texto de recuperacao pode ser gerado
    hostil = cifrar_payload({"nome_cliente": _Hostil()}, cid)
    assert crypto.decifrar(hostil["nome_cliente"], contexto_payload("nome_cliente", cid)) == "[valor invalido descartado]"
    # e o inverso devolve strings (round-trip exato so para str)
    assert decifrar_payload(cifrar_payload({"nome_cliente": "José 😀"}, cid), cid)["nome_cliente"] == "José 😀"
    assert decifrar_payload(cifrar_payload({"nome_cliente": 123}, cid), cid)["nome_cliente"] == "123"  # texto, nao int


def test_cifrar_payload_usa_nonce_novo_e_aad_do_id_do_evento():
    a, b = uuid.uuid4(), uuid.uuid4()
    p1, p2 = cifrar_payload({"nome_cliente": "x"}, a), cifrar_payload({"nome_cliente": "x"}, a)
    assert p1["nome_cliente"] != p2["nome_cliente"]
    with pytest.raises(ErroDecifragem):
        decifrar_payload(p1, b)


# =====================================================================================================================
# H1 - teste estatico: todo ponto de gravacao de SyncEvento( passa por cifrar_payload
# =====================================================================================================================

def _chamadas_a_sync_evento(caminho: Path):
    import ast
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achadas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            f = no.func
            nome = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if nome == "SyncEvento":
                achadas.append(no)
    return achadas


def test_estatico_so_ha_dois_pontos_de_gravacao_de_sync_evento_e_ambos_usam_cifrar_payload():
    import ast
    sites = []
    for arquivo in sorted((BACKEND / "app").rglob("*.py")):
        for chamada in _chamadas_a_sync_evento(arquivo):
            payload_kw = [k for k in chamada.keywords if k.arg == "payload"]
            ok = (len(payload_kw) == 1 and isinstance(payload_kw[0].value, ast.Call)
                  and getattr(payload_kw[0].value.func, "id", None) == "cifrar_payload")
            sites.append((arquivo.relative_to(BACKEND).as_posix(), chamada.lineno, ok))
    assert [(a) for a, _l, _ok in sites] == ["app/services/sync_service.py"] * 2, sites
    assert all(ok for _a, _l, ok in sites), f"SyncEvento( sem cifrar_payload: {sites}"
    # nenhum outro caminho escreve em sync_evento: nem INSERT cru, nem Core insert, nem atribuicao a `.payload` de SyncEvento
    for arquivo in sorted((BACKEND / "app").rglob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8")
        assert not re.search(r"insert\s+into\s+sync_evento", fonte, re.I), arquivo
        assert not re.search(r"insert\(\s*SyncEvento", fonte), arquivo
        assert "SyncEvento.__table__.insert" not in fonte, arquivo
        if arquivo.name != "sync_evento.py":
            assert not re.search(r"\.payload\s*=(?!=)", fonte) or arquivo.name in ("auditoria_service.py", "log_acao.py"), arquivo


# =====================================================================================================================
# H1 - limites documentados (NAO sao defeitos novos; riscos para o parecer)
# =====================================================================================================================

def test_documenta_chave_pessoal_com_outro_nome_ou_aninhada_continua_em_claro(fluxo):
    """A cifragem e por lista BRANCA de chaves (CHAVES_PESSOAIS_PAYLOAD). O app legitimo so envia estas duas; um cliente
    que mande o dado sob outro nome (ou aninhado) o ve gravado em claro. Risco residual aceito/documentado."""
    _prep(fluxo)
    ev = _ev(fluxo, "tipo_que_nao_existe", {"Nome_Cliente": "SEGREDO variante", "dados": {"nome_cliente": "SEGREDO aninhado"}},
             AGORA() - timedelta(minutes=1))
    assert _res(_enviar_bruto(fluxo, [ev]))[0]["codigo"] == "VALIDACAO"
    texto = _linha_sync(ev["client_event_id"])["payload_texto"]
    assert "SEGREDO variante" in texto and "SEGREDO aninhado" in texto


def test_outras_chaves_do_payload_com_nul_ou_surrogate_ficam_em_claro_e_o_evento_e_gravado_no_sqlite(fluxo):
    """ACHADO do Backend (pre-existente, NAO corrigido): chaves fora de CHAVES_PESSOAIS_PAYLOAD seguem no JSONB em claro.
    No SQLite o INSERT funciona e o valor e preservado (escapado no JSON). Comportamento atual registrado aqui."""
    _prep(fluxo)
    ev = _ev(fluxo, "tipo_que_nao_existe", {"motivo": "a\x00b", "descricao": "c\ud800d"}, AGORA() - timedelta(minutes=1))
    r = _enviar_bruto(fluxo, [ev])
    assert r.status_code == 200 and _res(r)[0]["codigo"] == "VALIDACAO"
    payload = _linha_sync(ev["client_event_id"])["payload"]
    assert payload["motivo"] == "a\x00b" and payload["descricao"] == "c\ud800d"  # em claro, nao cifrado


@pytest.mark.xfail(strict=True, reason="RISCO (pre-existente, Backend): NUL/surrogate isolado em chaves NAO cifradas do payload "
                                       "(ex. motivo, descricao) sao gravados em JSONB. O PostgreSQL recusa \\u0000 e surrogate "
                                       "isolado em JSONB => o db.flush() do evento falha e o lote pode virar 500 (evento nao "
                                       "registrado; idempotencia SY-03 quebrada). Nao verificavel em SQLite.")
def test_xfail_chaves_nao_cifradas_nao_deveriam_gravar_nul_ou_surrogate_no_jsonb(fluxo):
    _prep(fluxo)
    ev = _ev(fluxo, "tipo_que_nao_existe", {"motivo": "a\x00b", "descricao": "c\ud800d"}, AGORA() - timedelta(minutes=1))
    _enviar_bruto(fluxo, [ev])
    texto = _linha_sync(ev["client_event_id"])["payload_texto"]
    # esperado para ser seguro em PostgreSQL: nenhum \u0000 nem surrogate (\ud800..\udfff) no JSON gravado
    assert "\\u0000" not in texto and not re.search(r"\\ud[89a-f][0-9a-f]{2}", texto, re.I)


# =====================================================================================================================
# H2 - CA-V07-5: cliente
# =====================================================================================================================

def _bruto_cliente(id_cliente: int):
    return _bruto("SELECT contato_principal_nome, contato_principal_telefone, telefone FROM cliente WHERE id_cliente=:i",
                  i=id_cliente)[0]


def test_ca_v07_5_post_cliente_grava_contato_cifrado_a_api_devolve_em_claro_e_telefone_comercial_nao(client, admin):
    corpo = payload_cliente(contato_principal_nome="SEGREDO Sylvia Rodrigues Ç 😀", contato_principal_telefone="(27) 99999-0001")
    r = client.post("/api/clientes/", json=corpo, headers=admin.headers)
    assert r.status_code == 201, r.text
    assert r.json()["contato_principal_nome"] == corpo["contato_principal_nome"]
    assert r.json()["contato_principal_telefone"] == corpo["contato_principal_telefone"]
    nome, tel, comercial = _bruto_cliente(r.json()["id_cliente"])
    assert nome.startswith("enc1:") and tel.startswith("enc1:")
    assert "SEGREDO" not in nome and "99999" not in tel
    assert crypto.decifrar(nome, "cliente.contato_principal_nome") == corpo["contato_principal_nome"]
    assert crypto.decifrar(tel, "cliente.contato_principal_telefone") == corpo["contato_principal_telefone"]
    assert comercial == corpo["telefone"]  # decisao D5 do PO: telefone comercial (PJ) segue em claro
    # leituras pela API (lista e por id) tambem em claro
    por_id = client.get(f"/api/clientes/{r.json()['id_cliente']}", headers=admin.headers).json()
    assert por_id["contato_principal_nome"] == corpo["contato_principal_nome"]
    lista = client.get("/api/clientes/", headers=admin.headers).json()
    assert lista[0]["contato_principal_telefone"] == corpo["contato_principal_telefone"]


def test_ca_v07_5_contato_ausente_fica_null_e_nao_vira_enc1(client, admin):
    r = client.post("/api/clientes/", json=payload_cliente(), headers=admin.headers)
    assert r.status_code == 201, r.text
    assert _bruto_cliente(r.json()["id_cliente"])[:2] == (None, None)
    assert r.json()["contato_principal_nome"] is None


@pytest.mark.parametrize("campo,limite", [("contato_principal_nome", 100), ("contato_principal_telefone", 20)])
def test_ca_v07_5_validacao_100_e_20_continua_valendo_antes_de_cifrar(client, admin, campo, limite):
    ok = client.post("/api/clientes/", json=payload_cliente(**{campo: "ç" * limite}), headers=admin.headers)
    assert ok.status_code == 201, ok.text
    assert ok.json()[campo] == "ç" * limite  # exatamente no limite: aceito e devolvido inteiro
    antes = _bruto("SELECT count(*) FROM cliente")[0][0]
    ruim = client.post("/api/clientes/", json=payload_cliente(**{campo: "ç" * (limite + 1)}), headers=admin.headers)
    assert ruim.status_code == 422, ruim.text
    assert _bruto("SELECT count(*) FROM cliente")[0][0] == antes  # nada gravado (nem cifrado) quando a validacao falha
    # o limite vale em CARACTERES do texto claro, nao do texto cifrado (que e bem maior)
    id_ok = ok.json()["id_cliente"]
    assert len(_bruto_cliente(id_ok)[0 if campo.endswith("nome") else 1]) > limite


@pytest.mark.parametrize("campo", ["contato_principal_nome", "contato_principal_telefone"])
def test_post_e_patch_de_cliente_recusam_nul_com_422(client, admin, campo):
    antes = _bruto("SELECT count(*) FROM cliente")[0][0]
    cab = {**admin.headers, "Content-Type": "application/json"}
    r = client.post("/api/clientes/", content=json.dumps(payload_cliente(**{campo: "a\x00b"})), headers=cab)
    assert r.status_code == 422, r.text
    assert _bruto("SELECT count(*) FROM cliente")[0][0] == antes
    ok = client.post("/api/clientes/", json=payload_cliente(), headers=admin.headers).json()
    r = client.patch(f"/api/clientes/{ok['id_cliente']}", content=json.dumps({campo: "a\x00b"}), headers=cab)
    assert r.status_code == 422, r.text
    assert _bruto_cliente(ok["id_cliente"])[:2] == (None, None)


def _requisicoes_com_surrogate(admin, fluxo=None):
    """(rotulo, metodo, url, corpo_json_ascii, headers) de cada rota REST que recebe texto cifrado em repouso."""
    base = {**admin.headers, "Content-Type": "application/json"}
    for campo in ("contato_principal_nome", "contato_principal_telefone"):
        yield (f"POST cliente {campo}", "post", "/api/clientes/", json.dumps(payload_cliente(**{campo: "a\ud800b"})), base)
    yield ("PATCH cliente", "patch", "/api/clientes/{id}", json.dumps({"contato_principal_nome": "a\udfffb"}), base)
    if fluxo is not None:
        cab = {**fluxo.tecnico.headers, "Content-Type": "application/json"}
        for nome, doc in (("a\ud800b", CPF_VALIDO), ("Maria", "\ud800")):
            yield (f"finalizar-atendimento {nome!r}", "post", fluxo.url("finalizar-atendimento"),
                   json.dumps({"nome_cliente": nome, "documento_cliente": doc, "assinatura_base64": assinatura_b64()}), cab)


def _disparar(sem_excecao, metodo, url, corpo, cab, id_cliente=None):
    return getattr(sem_excecao, metodo)(url.replace("{id}", str(id_cliente)), content=corpo, headers=cab)


def test_defeito_d_v07_3_surrogate_isolado_no_rest_hoje_responde_500_e_nao_grava_nada(client, admin, fluxo):
    """COMPORTAMENTO REAL (registrado; ver o xfail abaixo): o pydantic ja recusa surrogate isolado em `str`
    (`string_unicode`), mas o corpo do 422 repete o `input` e o Starlette nao consegue serializa-lo (UnicodeEncodeError)
    => HTTP 500 em vez de 422. Nada e gravado. Classe pre-existente (vale para qualquer campo str); a decisao do PO
    previa 422 e `validar_texto_armazenavel` nunca chega a rodar para surrogate no REST."""
    fluxo.ate_em_atendimento()
    fluxo.conserto_completo(estrito=True)
    ok = client.post("/api/clientes/", json=payload_cliente(), headers=admin.headers).json()
    sem_excecao = _cliente_sem_excecao()
    antes = _bruto("SELECT count(*) FROM cliente")[0][0]
    for rotulo, metodo, url, corpo, cab in _requisicoes_com_surrogate(admin, fluxo):
        r = _disparar(sem_excecao, metodo, url, corpo, cab, ok["id_cliente"])
        assert r.status_code == 500, (rotulo, r.status_code)
    assert _bruto("SELECT count(*) FROM cliente")[0][0] == antes
    assert _bruto_cliente(ok["id_cliente"])[:2] == (None, None)
    assert _bruto("SELECT nome_cliente_assinatura, documento_cliente FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0] == (None, None)


@pytest.mark.xfail(strict=True, reason="DEFEITO D-V07-3: surrogate isolado em texto REST responde 500 (UnicodeEncodeError ao "
                                       "serializar o corpo do 422), nao 422/VALIDACAO como decidido pelo PO.")
def test_xfail_surrogate_isolado_no_rest_deveria_ser_422(client, admin, fluxo):
    fluxo.ate_em_atendimento()
    fluxo.conserto_completo(estrito=True)
    ok = client.post("/api/clientes/", json=payload_cliente(), headers=admin.headers).json()
    sem_excecao = _cliente_sem_excecao()
    for rotulo, metodo, url, corpo, cab in _requisicoes_com_surrogate(admin, fluxo):
        assert _disparar(sem_excecao, metodo, url, corpo, cab, ok["id_cliente"]).status_code == 422, rotulo


def test_texto_vazio_ou_so_espacos_no_contato_e_aceito_e_cifrado(client, admin):
    """Comportamento real: o contato aceita '' (sem min_length) e vira enc1:...; a API devolve ''. Registrado."""
    r = client.post("/api/clientes/", json=payload_cliente(contato_principal_nome="   ", contato_principal_telefone=""),
                    headers=admin.headers)
    assert r.status_code == 201, r.text
    assert r.json()["contato_principal_nome"] == "" and r.json()["contato_principal_telefone"] == ""
    nome, tel, _ = _bruto_cliente(r.json()["id_cliente"])
    assert crypto.decifrar(nome, "cliente.contato_principal_nome") == "" and crypto.decifrar(tel, "cliente.contato_principal_telefone") == ""


def test_patch_cliente_cifra_null_explicito_limpa_e_parcial_nao_toca_nas_outras_colunas(client, admin):
    criado = client.post("/api/clientes/", json=payload_cliente(contato_principal_nome="SEGREDO Fulano",
                                                                  contato_principal_telefone="27999990000"),
                         headers=admin.headers).json()
    cid = criado["id_cliente"]
    nome0, tel0, _ = _bruto_cliente(cid)
    # parcial: so o telefone do contato; o nome cifrado fica identico byte a byte (nao e recifrado)
    r = client.patch(f"/api/clientes/{cid}", json={"contato_principal_telefone": "27988887777"}, headers=admin.headers)
    assert r.status_code == 200 and r.json()["contato_principal_telefone"] == "27988887777"
    assert r.json()["contato_principal_nome"] == "SEGREDO Fulano"
    nome1, tel1, _ = _bruto_cliente(cid)
    assert nome1 == nome0 and tel1 != tel0 and tel1.startswith("enc1:")
    assert crypto.decifrar(tel1, "cliente.contato_principal_telefone") == "27988887777"
    # parcial de OUTRO campo (razao social) nao mexe nos contatos
    assert client.patch(f"/api/clientes/{cid}", json={"razao_social": "Nova Razao"}, headers=admin.headers).status_code == 200
    assert _bruto_cliente(cid)[:2] == (nome1, tel1)
    # alteracao do nome: novo enc1 com validacao de tamanho
    assert client.patch(f"/api/clientes/{cid}", json={"contato_principal_nome": "x" * 101}, headers=admin.headers).status_code == 422
    assert _bruto_cliente(cid)[0] == nome1
    r = client.patch(f"/api/clientes/{cid}", json={"contato_principal_nome": "Beltrano Çã 😀"}, headers=admin.headers)
    assert r.status_code == 200 and r.json()["contato_principal_nome"] == "Beltrano Çã 😀"
    assert _bruto_cliente(cid)[0] not in (nome0, nome1)
    # null EXPLICITO limpa (NULL no banco, nao enc1 de "None") e a API devolve null
    r = client.patch(f"/api/clientes/{cid}", json={"contato_principal_nome": None, "contato_principal_telefone": None},
                     headers=admin.headers)
    assert r.status_code == 200, r.text
    assert r.json()["contato_principal_nome"] is None and r.json()["contato_principal_telefone"] is None
    assert _bruto_cliente(cid)[:2] == (None, None)


def test_aad_por_coluna_troca_de_colunas_e_detectada_mas_troca_entre_clientes_nao_e_limite_herdado(client, admin, db):
    """Limite herdado (SDD 8.1): a AAD do contato e por COLUNA. Trocar nome<->telefone do mesmo cliente falha; copiar o
    valor cifrado de um cliente para OUTRO decifra sem erro (NAO detectado). Registra o comportamento real."""
    a = client.post("/api/clientes/", json=payload_cliente(contato_principal_nome="SEGREDO Alfa",
                                                             contato_principal_telefone="111"), headers=admin.headers).json()
    b = client.post("/api/clientes/", json=payload_cliente(contato_principal_nome="SEGREDO Beta",
                                                             contato_principal_telefone="222"), headers=admin.headers).json()
    na, ta, _ = _bruto_cliente(a["id_cliente"])
    nb, _tb, _ = _bruto_cliente(b["id_cliente"])
    with engine.begin() as conn:  # entre clientes
        conn.execute(text("UPDATE cliente SET contato_principal_nome=:n WHERE id_cliente=:i"), {"n": nb, "i": a["id_cliente"]})
    assert client.get(f"/api/clientes/{a['id_cliente']}", headers=admin.headers).json()["contato_principal_nome"] == "SEGREDO Beta"
    with engine.begin() as conn:  # entre colunas do mesmo cliente
        conn.execute(text("UPDATE cliente SET contato_principal_nome=:t, contato_principal_telefone=:n WHERE id_cliente=:i"),
                     {"t": ta, "n": na, "i": a["id_cliente"]})
    db.expire_all()
    with pytest.raises(ErroDecifragem):
        db.get(Cliente, a["id_cliente"]).contato_principal_nome


def test_modelos_declaram_as_colunas_novas_como_texto_cifrado_com_o_contexto_certo():
    from app.models.cliente import Cliente as C
    for modelo, coluna in ((C, "contato_principal_nome"), (C, "contato_principal_telefone"),
                           (Visita, "nome_cliente_assinatura"), (Visita, "documento_cliente")):
        tipo = modelo.__table__.c[coluna].type
        assert isinstance(tipo, TextoCifrado) and tipo.contexto == f"{modelo.__tablename__}.{coluna}"
    assert not isinstance(C.__table__.c.telefone.type, TextoCifrado)  # D5: comercial/PJ em claro


# ---- clientes com linha em CLARO (ENCRYPTION_ALLOW_LEGACY_PLAINTEXT=false): comportamento real -------------------------

def test_cliente_com_contato_em_claro_derruba_a_listagem_inteira_com_500_e_so_com_o_flag_legado_volta(client, admin, fluxo, monkeypatch):
    """COMPORTAMENTO REAL (registrado, ver defeito D-V07-2): com o flag desligado (padrao/producao), UMA linha de `cliente` com
    contato em texto puro faz GET /api/clientes/ falhar (500) para TODOS os clientes; o mesmo para PATCH/DELETE desse cliente
    e para a listagem de OS que carregue o cliente. Fail-closed (nao mostra dado), mas com raio de impacto grande."""
    bom = client.post("/api/clientes/", json=payload_cliente(contato_principal_nome="SEGREDO Bom"), headers=admin.headers).json()
    ruim = client.post("/api/clientes/", json=payload_cliente(), headers=admin.headers).json()
    Fluxo(client, admin, fluxo.tecnico, ruim["id_cliente"]).criar_os()  # OS do cliente "ruim", criada antes de corromper
    with engine.begin() as conn:  # equivale a um cliente legado nao migrado / linha editada no painel do Supabase
        conn.execute(text("UPDATE cliente SET contato_principal_nome='Texto Puro' WHERE id_cliente=:i"), {"i": ruim["id_cliente"]})
    sem_excecao = _cliente_sem_excecao()
    assert config.ENCRYPTION_ALLOW_LEGACY_PLAINTEXT is False
    assert sem_excecao.get("/api/clientes/", headers=admin.headers).status_code == 500  # lista TODA falha
    assert sem_excecao.get(f"/api/clientes/{ruim['id_cliente']}", headers=admin.headers).status_code == 500
    assert sem_excecao.patch(f"/api/clientes/{ruim['id_cliente']}", json={"razao_social": "Nova"}, headers=admin.headers).status_code == 500
    assert sem_excecao.delete(f"/api/clientes/{ruim['id_cliente']}", headers=admin.headers).status_code == 500  # nem desativa
    assert sem_excecao.get(f"/api/clientes/{bom['id_cliente']}", headers=admin.headers).status_code == 200  # os outros por id ok
    # OS do cliente ruim: a listagem de chamados carrega o cliente (relacao) e tambem falha
    assert sem_excecao.get("/api/chamados/", headers=admin.headers).status_code == 500
    # com o flag de transicao (so dev/teste; recusado em producao) a linha em claro e lida como esta
    monkeypatch.setattr(config, "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT", True)
    lista = sem_excecao.get("/api/clientes/", headers=admin.headers)
    assert lista.status_code == 200
    assert {c["contato_principal_nome"] for c in lista.json()} >= {"SEGREDO Bom", "Texto Puro"}


# =====================================================================================================================
# H2 - CA-V07-6: selo de integridade com o nome cifrado
# =====================================================================================================================

NOME_SELO = "Zé  da Silva Ç Jr 😀 José"  # espaco duplo, NBSP interno, emoji e acento decomposto (NFD)


def test_ca_v07_6_selo_continua_integro_antes_e_depois_de_o_script_cifrar_o_nome_de_visita_ja_selada(fluxo, db, monkeypatch):
    _finalizar_com(fluxo, NOME_SELO)
    selo = _bruto("SELECT selo_integridade FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0][0]
    # reproduz o ESTADO LEGADO (visita selada na v0.6 com o nome em claro): grava o claro por SQL cru
    claro = crypto.decifrar(_bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0][0],
                            "visita.nome_cliente_assinatura")
    assert claro == NOME_SELO
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": claro, "i": fluxo.visita_id})
    monkeypatch.setattr(config, "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT", True)  # fase de transicao: le o claro
    db.expire_all()
    antes = _verificar(fluxo).json()
    assert antes["estado"] == "integro" and antes["visitas"][0]["motivos"] == [], antes

    mod = _carregar_script()
    feito = mod.cifrar_campos(engine)
    assert feito == {"visita.nome_cliente_assinatura": 1}  # so este valor estava em claro
    monkeypatch.setattr(config, "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT", False)  # estado final: claro em coluna cifrada = erro
    bruto = _bruto("SELECT nome_cliente_assinatura, selo_integridade FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0]
    assert bruto[0].startswith("enc1:") and bruto[1] == selo  # cifrado; o selo gravado NAO mudou
    db.expire_all()
    depois = _verificar(fluxo).json()
    assert depois["estado"] == "integro" and depois["visitas"][0]["motivos"] == [], depois
    assert fluxo.os()["visitas"][0]["nome_cliente_assinatura"] == NOME_SELO  # inclusive NBSP/espaco duplo/NFD, sem normalizar
    assert mod.cifrar_campos(engine) == {}  # 2a execucao nao faz nada


def test_selo_nome_cifrado_valido_de_outro_nome_gravado_por_sql_cru_vira_selo_divergente(fluxo):
    _finalizar_com(fluxo, "Maria Gerente")
    forjado = crypto.cifrar("Fraudador", "visita.nome_cliente_assinatura")  # um enc1: VALIDO, de outro nome
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": forjado, "i": fluxo.visita_id})
    corpo = _verificar(fluxo).json()
    assert corpo["estado"] == "adulterado" and corpo["visitas"][0]["motivos"] == ["selo_divergente"]


def test_selo_troca_do_nome_cifrado_entre_duas_visitas_seladas_vira_selo_divergente_nas_duas(fluxo):
    f1, f2 = fluxo, _novo_fluxo(fluxo)
    _finalizar_com(f1, "SEGREDO Primeiro")
    _finalizar_com(f2, "SEGREDO Segundo")
    n1 = _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=f1.visita_id)[0][0]
    n2 = _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=f2.visita_id)[0][0]
    assert _verificar(f1).json()["estado"] == "integro" and _verificar(f2).json()["estado"] == "integro"
    with engine.begin() as conn:  # AAD por coluna: a troca DECIFRA sem erro; so o selo pega
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": n2, "i": f1.visita_id})
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": n1, "i": f2.visita_id})
    assert f1.os()["visitas"][0]["nome_cliente_assinatura"] == "SEGREDO Segundo"  # a API nao acusa sozinha
    for f in (f1, f2):
        corpo = _verificar(f).json()
        assert corpo["estado"] == "adulterado" and "selo_divergente" in corpo["visitas"][0]["motivos"], corpo


def test_selo_visita_legada_sem_selo_com_nome_trocado_nao_e_detectada_limite_documentado(fluxo):
    """LIMITE DOCUMENTADO: visita finalizada antes do selo (`sem_selo`, sem registro no log_acao) nao tem como detectar a
    troca do nome cifrado entre visitas (AAD por coluna). Aceito pela SDD 8.1 (legado nao e selado retroativamente)."""
    from app.models.log_acao import LogAcao
    f1, f2 = fluxo, _novo_fluxo(fluxo)
    _finalizar_com(f1, "SEGREDO Primeiro")
    _finalizar_com(f2, "SEGREDO Segundo")
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET selo_integridade=NULL, selo_versao=NULL"))
    from sqlalchemy.orm import Session
    with Session(engine) as s:  # apaga o selo tambem do log_acao: visita realmente "legada"
        for reg in s.query(LogAcao).filter(LogAcao.acao == "ATENDIMENTO_FINALIZADO").all():
            reg.payload = {k: v for k, v in reg.payload.items() if k not in ("selo", "selo_versao")}
        s.commit()
    n1 = _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=f1.visita_id)[0][0]
    n2 = _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=f2.visita_id)[0][0]
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": n2, "i": f1.visita_id})
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"), {"n": n1, "i": f2.visita_id})
    for f in (f1, f2):
        assert _verificar(f).json()["estado"] == "sem_selo"  # NAO detecta
    assert f1.os()["visitas"][0]["nome_cliente_assinatura"] == "SEGREDO Segundo"


def test_selo_texto_puro_ou_enc1_adulterado_em_coluna_cifrada_vira_laudo_adulterado_sem_500(fluxo, monkeypatch):
    """D-V07-1 CORRIGIDO: com o flag desligado, texto puro (ou enc1: que nao autentica) em `visita.nome_cliente_assinatura`
    ou `documento_cliente` faz `verificar-integridade` responder 200 com `estado: adulterado` e motivo
    `campo_cifrado_invalido:<coluna>` (sem expor valor) - nunca `integro`, nunca 500. O GET da propria OS segue fail-closed
    (500, aceito pelo PO). Com o flag legado ligado, o laudo e `adulterado` por `selo_divergente`."""
    _finalizar_com(fluxo, "Maria Gerente")
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura='Fraudador' WHERE id_visita=:i"), {"i": fluxo.visita_id})
    sem_excecao = _cliente_sem_excecao()
    url = f"/api/chamados/{fluxo.os_id}/verificar-integridade"
    r = sem_excecao.get(url, headers=fluxo.admin.headers)
    assert r.status_code == 200 and "Fraudador" not in r.text and "integro" not in r.json()["estado"]
    assert r.json()["estado"] == "adulterado"
    assert r.json()["visitas"][0]["motivos"] == ["campo_cifrado_invalido:nome_cliente_assinatura"]
    assert sem_excecao.get(f"/api/chamados/{fluxo.os_id}", headers=fluxo.admin.headers).status_code == 500
    # enc1: com 1 byte alterado: idem
    valido = crypto.cifrar("Maria Gerente", "visita.nome_cliente_assinatura")
    bruto = bytearray(base64.b64decode(valido[5:]))
    bruto[-1] ^= 1
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura=:n WHERE id_visita=:i"),
                     {"n": "enc1:" + base64.b64encode(bytes(bruto)).decode(), "i": fluxo.visita_id})
    r = sem_excecao.get(url, headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["estado"] == "adulterado"
    assert r.json()["visitas"][0]["motivos"] == ["campo_cifrado_invalido:nome_cliente_assinatura"]
    # documento_cliente tambem (texto puro) e os dois campos juntos
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET documento_cliente='52998224725' WHERE id_visita=:i"), {"i": fluxo.visita_id})
    r = sem_excecao.get(url, headers=fluxo.admin.headers)
    assert r.status_code == 200 and r.json()["estado"] == "adulterado" and "52998224725" not in r.text
    assert sorted(r.json()["visitas"][0]["motivos"]) == ["campo_cifrado_invalido:documento_cliente",
                                                         "campo_cifrado_invalido:nome_cliente_assinatura"]
    # fase de transicao (flag legado ligado): o texto puro e lido e o selo acusa
    with engine.begin() as conn:
        conn.execute(text("UPDATE visita SET nome_cliente_assinatura='Fraudador', documento_cliente=:d WHERE id_visita=:i"),
                     {"d": crypto.cifrar("52998224725", "visita.documento_cliente"), "i": fluxo.visita_id})
    monkeypatch.setattr(config, "ENCRYPTION_ALLOW_LEGACY_PLAINTEXT", True)
    corpo = sem_excecao.get(url, headers=fluxo.admin.headers).json()
    assert corpo["estado"] == "adulterado" and "selo_divergente" in corpo["visitas"][0]["motivos"]


def test_finalizar_atendimento_recusa_nul_com_422_e_nao_grava_nada(fluxo):
    fluxo.ate_em_atendimento()
    fluxo.conserto_completo(estrito=True)
    cab = {**fluxo.tecnico.headers, "Content-Type": "application/json"}
    for nome, doc in (("a\x00b", CPF_VALIDO), ("Maria", "529\x00.982.247-25")):
        corpo = json.dumps({"nome_cliente": nome, "documento_cliente": doc, "assinatura_base64": assinatura_b64()})
        r = fluxo.c.post(fluxo.url("finalizar-atendimento"), content=corpo, headers=cab)
        assert r.status_code == 422, (nome, doc, r.text)
    assert _bruto("SELECT nome_cliente_assinatura, documento_cliente, assinatura_url FROM visita WHERE id_visita=:i",
                  i=fluxo.visita_id)[0] == (None, None, None)


def test_sync_finalizar_com_nul_ou_surrogate_no_nome_e_rejeitado_como_validacao_com_payload_cifrado(fluxo):
    """No sync a recusa NAO sofre o defeito D-V07-3: o ValidationError e capturado e o resultado e `rejeitado/VALIDACAO`."""
    _pronto_para_finalizar(fluxo)
    f_ass, _ = _arquivo(fluxo, "assinatura")
    resultados = []
    for i, nome in enumerate(("SEGREDO\x00fim", "SEGREDO\ud800fim")):
        fluxo_i = fluxo
        ev = _ev(fluxo_i, "atendimento_finalizado", {"nome_cliente": nome, "documento_cliente": CPF_VALIDO,
                                                     "assinatura_ref": f_ass}, AGORA() - timedelta(minutes=2 - i))
        r = _res(_enviar_bruto(fluxo_i, [ev]))[0]
        assert (r["resultado"], r["codigo"]) == ("rejeitado", "VALIDACAO") and "SEGREDO" not in json.dumps(r)
        resultados.append(_conferir_payload_cifrado(ev["client_event_id"], nome, chaves=("nome_cliente",)))
    assert _bruto("SELECT nome_cliente_assinatura FROM visita WHERE id_visita=:i", i=fluxo.visita_id)[0][0] is None


# =====================================================================================================================
# Script: CA-V07-7 (campos novos + payload de sync_evento)
# =====================================================================================================================

def _snapshot(eng) -> dict:
    with eng.connect() as c:
        return {t: [tuple(r) for r in c.execute(text(f"SELECT * FROM {t} ORDER BY 1")).fetchall()]
                for t in ("tecnico", "visita", "cliente", "sync_evento")}


def test_ca_v07_7_script_cifra_campos_e_payload_e_a_segunda_execucao_e_zero(banco_legado):
    mod = _carregar_script()
    campos = mod.cifrar_campos(banco_legado)
    assert campos["cliente.contato_principal_nome"] == 2 and campos["cliente.contato_principal_telefone"] == 1
    assert campos["visita.nome_cliente_assinatura"] == 1 and campos["visita.documento_cliente"] == 1
    payload = mod.cifrar_payload_sync(banco_legado)
    assert payload["sync_evento.payload.nome_cliente"] == 4 and payload["sync_evento.payload.documento_cliente"] == 3
    assert payload["eventos"] == 4 and "anomalias" not in payload
    assert all(v == 0 for v in mod.verificar_campos(banco_legado).values())
    contagens, ids = mod.verificar_payload_sync(banco_legado)
    assert all(v == 0 for v in contagens.values()) and ids == []
    # 2a execucao = 0 alteracoes, e nenhum byte muda (nao re-cifra, nonce nao muda)
    antes = _snapshot(banco_legado)
    assert mod.cifrar_campos(banco_legado) == {} and mod.cifrar_payload_sync(banco_legado) == {}
    assert _snapshot(banco_legado) == antes


def test_script_payload_cifrado_decifra_com_a_aad_por_linha_e_e_compativel_com_o_runtime(banco_legado):
    mod = _carregar_script()
    mod.cifrar_payload_sync(banco_legado)
    with banco_legado.connect() as c:
        linhas = mod._linhas_sync(c)
        por_id = {str(i): p for i, p in linhas}
    e1 = por_id[EVENTOS["aplicado"]]
    assert crypto.decifrar(e1["nome_cliente"], f"sync_evento.nome_cliente|{EVENTOS['aplicado']}") == "SEGREDO Maria 😀"
    # o script e o runtime concordam na AAD: decifrar_payload (runtime) abre o que o script cifrou
    assert decifrar_payload(e1, uuid.UUID(EVENTOS["aplicado"]))["documento_cliente"] == "529.982.247-25"
    assert e1["assinatura_ref"] == "ref-1" and e1["ocorrido_em_original"] == "2026-11-10T10:00:00+00:00"
    # e o inverso: o que o RUNTIME cifra o script reconhece como valido (nao e anomalia nem pendencia)
    novo = uuid.uuid4()
    runtime = cifrar_payload({"nome_cliente": "SEGREDO R", "documento_cliente": "52998224725"}, novo)
    with banco_legado.begin() as c:
        c.execute(insert(SyncEvento.__table__).values(client_event_id=novo, id_tecnico=1, tipo="x", resultado="aplicado",
                                                      ocorrido_em=datetime.now(timezone.utc), payload=runtime))
    contagens, ids = mod.verificar_payload_sync(banco_legado)
    assert all(v == 0 for v in contagens.values()) and ids == []
    # nao-dict (lista/string/numero) e ignorado sem derrubar o script; None dentro do dict segue None
    assert EVENTOS["nao_dict_lista"] not in por_id and EVENTOS["nao_dict_texto"] not in por_id
    assert por_id[EVENTOS["rejeitado_none"]]["documento_cliente"] is None


def test_script_dry_run_nao_grava_nada_em_nenhuma_tabela(banco_legado):
    mod = _carregar_script()
    antes = _snapshot(banco_legado)
    campos = mod.cifrar_campos(banco_legado, dry_run=True)
    payload = mod.cifrar_payload_sync(banco_legado, dry_run=True)
    assert campos["cliente.contato_principal_nome"] == 2 and payload["eventos"] == 4  # conta o que FARIA
    assert _snapshot(banco_legado) == antes  # mas nao gravou um byte
    assert any(v > 0 for v in mod.verificar_campos(banco_legado).values())


def test_script_decifrar_faz_round_trip_exato_para_strings_e_texto_json_para_nao_strings(banco_legado):
    mod = _carregar_script()
    original = _snapshot(banco_legado)
    mod.cifrar_campos(banco_legado)
    mod.cifrar_payload_sync(banco_legado)
    assert _snapshot(banco_legado) != original
    campos = mod.decifrar_campos(banco_legado)
    payload = mod.decifrar_payload_sync(banco_legado)
    assert campos["cliente.contato_principal_nome"] == 2 and payload["eventos"] == 4
    depois = _snapshot(banco_legado)
    # tabelas de campos: identicas (exceto tecnico.cnpj_idx, que o --decifrar mantem de proposito)
    assert depois["visita"] == original["visita"] and depois["cliente"] == original["cliente"]
    assert [r[:-1] for r in depois["tecnico"]] == [r[:-1] for r in original["tecnico"]]
    # payload: strings voltam EXATAS (acentos, emoji, '' e None); nao-strings voltam como TEXTO JSON (documentado)
    with banco_legado.connect() as c:
        por_id = {str(i): p for i, p in mod._linhas_sync(c)}
    assert por_id[EVENTOS["aplicado"]]["nome_cliente"] == "SEGREDO Maria 😀"
    assert por_id[EVENTOS["aplicado"]]["documento_cliente"] == "529.982.247-25"
    assert por_id[EVENTOS["rejeitado_none"]] == {"nome_cliente": "", "documento_cliente": None}
    assert por_id[EVENTOS["nao_string"]]["nome_cliente"] == "52998224725"  # era int -> agora texto
    assert por_id[EVENTOS["nao_string"]]["documento_cliente"] == '{"cpf": "52998224725"}'  # era dict -> texto JSON
    assert por_id[EVENTOS["sem_pessoal"]] == {"km_inicio": 5}
    assert mod.decifrar_campos(banco_legado) == {} and mod.decifrar_payload_sync(banco_legado) == {}  # idempotente


def test_script_decifrar_dry_run_nao_grava(banco_legado):
    mod = _carregar_script()
    mod.cifrar_campos(banco_legado)
    mod.cifrar_payload_sync(banco_legado)
    cifrado = _snapshot(banco_legado)
    assert mod.decifrar_campos(banco_legado, dry_run=True)["cliente.contato_principal_nome"] == 2
    assert mod.decifrar_payload_sync(banco_legado, dry_run=True)["eventos"] == 4
    assert _snapshot(banco_legado) == cifrado


# ---- anomalia: enc1: que nao decifra --------------------------------------------------------------------------------

def _inserir_evento(eng, payload, cid=None):
    cid = cid or uuid.uuid4()
    with eng.begin() as c:
        c.execute(insert(SyncEvento.__table__).values(client_event_id=cid, id_tecnico=1, tipo="x", resultado="rejeitado",
                                                      ocorrido_em=datetime.now(timezone.utc), payload=payload))
    return cid


def test_anomalia_enc1_que_nao_decifra_e_reportada_por_id_e_nao_derruba_o_decifrar_das_demais_linhas(banco_legado):
    mod = _carregar_script()
    ok = _inserir_evento(banco_legado, {"nome_cliente": "SEGREDO ok"})
    mod.cifrar_payload_sync(banco_legado)  # cifra o fixture e a linha `ok`
    ruim = _inserir_evento(banco_legado, {"nome_cliente": "enc1:AAAA", "documento_cliente": "529.982.247-25"})
    valor_de_outra_linha = crypto.cifrar("SEGREDO Z", contexto_payload("nome_cliente", uuid.uuid4()))
    trocado = _inserir_evento(banco_legado, {"nome_cliente": valor_de_outra_linha})  # enc1: valido, mas de OUTRA linha
    # --verificar: a anomalia e contada a parte e o ID aparece (nunca o valor)
    contagens, ids = mod.verificar_payload_sync(banco_legado)
    assert contagens["sync_evento.payload_anomalo"] == 2 and str(ruim) in ids and str(trocado) in ids
    assert contagens["sync_evento.payload.documento_cliente"] == 1  # o CPF em claro da linha `ruim` e pendencia comum
    # --decifrar: nao derruba a transacao; mantem a anomalia como esta, reporta o id e decifra as demais linhas
    anomalias = []
    resumo = mod.decifrar_payload_sync(banco_legado, anomalias=anomalias)
    assert resumo["anomalias"] == 2 and sorted(anomalias) == sorted([str(ruim), str(trocado)])
    with banco_legado.connect() as c:
        por_id = {str(i): p for i, p in mod._linhas_sync(c)}
    assert por_id[str(ok)]["nome_cliente"] == "SEGREDO ok"
    assert por_id[str(ruim)]["nome_cliente"] == "enc1:AAAA" and por_id[str(trocado)]["nome_cliente"] == valor_de_outra_linha


def test_anomalia_no_cifrar_e_cifrada_por_cima_e_o_texto_original_e_recuperavel(banco_legado):
    mod = _carregar_script()
    ruim = _inserir_evento(banco_legado, {"nome_cliente": "enc1:AAAA"})
    anomalias = []
    resumo = mod.cifrar_payload_sync(banco_legado, anomalias=anomalias)
    assert resumo["anomalias"] == 1 and anomalias == [str(ruim)]
    with banco_legado.connect() as c:
        valor = dict(mod._linhas_sync(c))[ruim]["nome_cliente"]
    assert crypto.decifrar(valor, contexto_payload("nome_cliente", ruim)) == "enc1:AAAA"  # o texto "enc1:AAAA" foi preservado
    assert mod.verificar_payload_sync(banco_legado)[0]["sync_evento.payload_anomalo"] == 0  # agora e valido


def test_pk_uuid_e_aad_por_linha_funcionam_no_script_com_uuid_como_objeto_e_como_texto(banco_legado):
    mod = _carregar_script()
    cid = uuid.UUID("12345678-1234-5678-1234-567812345678")
    _inserir_evento(banco_legado, {"nome_cliente": "SEGREDO U"}, cid)
    mod.cifrar_payload_sync(banco_legado)
    with banco_legado.connect() as c:
        valor = dict(mod._linhas_sync(c))[cid]["nome_cliente"]
    # AAD usa a forma canonica COM hifens, a mesma que o runtime usa (str(UUID))
    assert crypto.decifrar(valor, "sync_evento.nome_cliente|12345678-1234-5678-1234-567812345678") == "SEGREDO U"
    assert contexto_payload("nome_cliente", cid) == contexto_payload("nome_cliente", str(cid))
    with pytest.raises(ErroDecifragem):  # sem hifens (hex) nao abre: formato da AAD e rigido
        crypto.decifrar(valor, f"sync_evento.nome_cliente|{cid.hex}")


def test_payload_nao_dict_e_ignorado_sem_derrubar_o_script(banco_legado):
    mod = _carregar_script()
    for p in ([], [1, "x"], "texto", 5, None):
        _inserir_evento(banco_legado, p)
    antes_linhas = _snapshot(banco_legado)["sync_evento"]
    mod.cifrar_payload_sync(banco_legado)  # nao lanca
    mod.decifrar_payload_sync(banco_legado)
    assert mod.verificar_payload_sync(banco_legado)[0]["sync_evento.payload_anomalo"] == 0
    depois = {r[0]: r for r in _snapshot(banco_legado)["sync_evento"]}
    assert len(depois) == len(antes_linhas)


# ---- CLI: --verificar, selecao de escopo, pre-checagem ---------------------------------------------------------------

def _rodar(mod, monkeypatch, capsys, eng, *args) -> tuple:
    monkeypatch.setattr("app.db.database.engine", eng)  # main() importa `engine` na hora da chamada
    monkeypatch.setattr(sys, "argv", ["cifrar_dados_existentes.py", *args])
    codigo = mod.main()
    saida = capsys.readouterr().out
    return codigo, saida


def test_ca_v07_7_verificar_so_leitura_sai_com_1_se_ha_pendencia_e_0_se_completo(banco_legado, monkeypatch, capsys):
    mod = _carregar_script()
    antes = _snapshot(banco_legado)
    codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar")
    assert codigo == 1 and "ATENCAO" in saida and _snapshot(banco_legado) == antes  # somente leitura
    for segredo in ("SEGREDO", "529.982.247", "52998224725", "Silva", "Maria"):
        assert segredo not in saida  # so contagens e IDs
    assert EVENTOS["aplicado"] in saida  # ID, nao valor
    # restringir ao escopo: --payload-sync so olha o payload; --campos so as colunas
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar", "--payload-sync")[0] == 1
    mod.cifrar_payload_sync(banco_legado)
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar", "--payload-sync")[0] == 0
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar", "--campos")[0] == 1  # campos ainda pendentes
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar")[0] == 1  # tudo = campos + payload
    mod.cifrar_campos(banco_legado)
    codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar")
    assert codigo == 0 and "OK: nenhuma pendencia" in saida


def test_verificar_acusa_anomalia_com_codigo_1_mesmo_sem_nada_em_claro(banco_legado, monkeypatch, capsys):
    mod = _carregar_script()
    mod.cifrar_campos(banco_legado)
    mod.cifrar_payload_sync(banco_legado)
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar")[0] == 0
    ruim = _inserir_evento(banco_legado, {"nome_cliente": "enc1:AAAA"})
    codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, "--verificar")
    assert codigo == 1 and str(ruim) in saida and "enc1:AAAA" not in saida


def test_main_dry_run_nao_grava_e_main_real_grava_e_verifica(banco_legado, monkeypatch, capsys):
    mod = _carregar_script()
    antes = _snapshot(banco_legado)
    codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, "--dry-run", "--campos", "--payload-sync")
    assert codigo == 0 and _snapshot(banco_legado) == antes and "DRY-RUN" in saida
    codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, "--campos", "--payload-sync")
    assert codigo == 0 and "OK: nenhuma pendencia" in saida
    for segredo in ("SEGREDO", "529.982.247", "52998224725", "Silva"):
        assert segredo not in saida
    codigo, _ = _rodar(mod, monkeypatch, capsys, banco_legado, "--decifrar")
    assert codigo == 0
    assert _snapshot(banco_legado)["cliente"] == antes["cliente"] and _snapshot(banco_legado)["visita"] == antes["visita"]


def test_precheck_colunas_nao_text_aborta_com_codigo_2_antes_de_gravar_e_payload_sync_nao_e_bloqueado(banco_legado, monkeypatch, capsys):
    mod = _carregar_script()
    monkeypatch.setattr(mod, "colunas_nao_text", lambda eng: ["cliente.contato_principal_nome", "visita.nome_cliente_assinatura"])
    antes = _snapshot(banco_legado)
    for args in ((), ("--campos",)):
        codigo, saida = _rodar(mod, monkeypatch, capsys, banco_legado, *args)
        assert codigo == 2 and "ABORTADO" in saida and "--payload-sync" in saida
        assert _snapshot(banco_legado) == antes  # NADA gravado (nem payload, nem tecnico): aborta antes de qualquer escrita
    # H1 sozinho (sem DDL) nao depende da 0014: roda mesmo com as colunas ainda varchar
    codigo, _ = _rodar(mod, monkeypatch, capsys, banco_legado, "--payload-sync")
    assert codigo == 0
    depois = _snapshot(banco_legado)
    assert depois["cliente"] == antes["cliente"] and depois["visita"] == antes["visita"] and depois["sync_evento"] != antes["sync_evento"]
    # --dry-run tambem passa pela pre-checagem de campos
    assert _rodar(mod, monkeypatch, capsys, banco_legado, "--dry-run", "--campos")[0] == 2


def test_colunas_nao_text_logica_postgresql_com_engine_simulado_e_pula_no_sqlite(banco_legado):
    """A consulta a information_schema NAO e verificavel em SQLite: aqui so a logica (engine falso). No SQLite pula."""
    mod = _carregar_script()
    assert mod.colunas_nao_text(banco_legado) == []  # SQLite: nao checa

    class _Conn:
        def __init__(self, tipos):
            self.tipos = tipos

        def execute(self, _sql, params):
            return type("R", (), {"fetchall": lambda s: list(self.tipos[params["t"]].items())})()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Eng:
        def __init__(self, tipos):
            self.dialect = type("D", (), {"name": "postgresql"})()
            self._c = _Conn(tipos)

        def connect(self):
            return self._c

    todos_text = {"tecnico": {c: "text" for c in ("cnpj", "cpf", "telefone", "banco", "agencia", "conta", "pix")},
                  "visita": {"documento_cliente": "text", "nome_cliente_assinatura": "text"},
                  "cliente": {"contato_principal_nome": "text", "contato_principal_telefone": "text"}}
    assert mod.colunas_nao_text(_Eng(todos_text)) == []
    antes_da_0014 = {**todos_text, "cliente": {"contato_principal_nome": "character varying", "contato_principal_telefone": "character varying"},
                     "visita": {"documento_cliente": "text", "nome_cliente_assinatura": "character varying"}}
    assert mod.colunas_nao_text(_Eng(antes_da_0014)) == ["visita.nome_cliente_assinatura", "cliente.contato_principal_nome",
                                                         "cliente.contato_principal_telefone"]
    ausente = {**todos_text, "visita": {"documento_cliente": "text"}}  # coluna inexistente tambem e "nao text"
    assert mod.colunas_nao_text(_Eng(ausente)) == ["visita.nome_cliente_assinatura"]


# =====================================================================================================================
# CA-V07-8 e migracao: testes ESTATICOS (o SQL nao pode ser executado em SQLite)
# =====================================================================================================================

def _sql(nome: str) -> str:
    return (BACKEND / "migrations" / nome).read_text(encoding="utf-8")


def _sem_comentarios(sql: str) -> str:
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def test_ca_v07_8_migracao_0014_converte_as_tres_colunas_para_text_e_nao_toca_no_resto():
    codigo = _sem_comentarios(_sql("0014_cifragem_contatos.sql"))
    assert re.search(r"ALTER TABLE public\.cliente\s+ALTER COLUMN contato_principal_nome\s+TYPE text,\s+"
                     r"ALTER COLUMN contato_principal_telefone\s+TYPE text;", codigo)
    assert re.search(r"ALTER TABLE public\.visita ALTER COLUMN nome_cliente_assinatura TYPE text;", codigo)
    alteradas = re.findall(r"ALTER COLUMN\s+(\w+)\s+TYPE\s+(\w+)", codigo)
    assert sorted(alteradas) == sorted([("contato_principal_nome", "text"), ("contato_principal_telefone", "text"),
                                        ("nome_cliente_assinatura", "text")])
    assert "telefone TYPE" not in codigo.replace("contato_principal_telefone", "") and "nome_ajudante" not in codigo  # D5 e H3
    assert not re.search(r"\b(UPDATE|INSERT|DELETE)\b", codigo, re.I)  # nao cifra nem altera dado
    assert "BEGIN;" in codigo and codigo.rstrip().endswith("COMMIT;") and "lock_timeout" in codigo
    assert "to_regclass" in codigo and "information_schema.columns" in codigo  # checagens de pre-condicao
    assert not re.search(r"sync_evento", codigo)  # H1 sem DDL


def test_ca_v07_8_rollback_aborta_se_restar_enc1_e_so_estreita_as_colunas_depois_da_trava():
    codigo = _sem_comentarios(_sql("0014_rollback.sql"))
    trava = codigo.index("RAISE EXCEPTION 'Ainda ha valores cifrados")
    primeiro_alter = codigo.index("ALTER TABLE")
    assert trava < primeiro_alter  # a trava vem ANTES de qualquer estreitamento
    bloco = codigo[:trava]
    for trecho in ("contato_principal_nome LIKE 'enc1:%'", "contato_principal_telefone LIKE 'enc1:%'",
                   "nome_cliente_assinatura LIKE 'enc1:%'", "payload ->> 'documento_cliente' LIKE 'enc1:%'",
                   "payload ->> 'nome_cliente' LIKE 'enc1:%'"):
        assert trecho in bloco, trecho  # colunas E payload do sync_evento
    assert "FROM public.sync_evento" in bloco
    # 2a trava: tamanho (nao deixar o ALTER TYPE varchar(n) falhar com erro generico)
    assert "char_length(contato_principal_nome) > 100" in codigo and "char_length(contato_principal_telefone) > 20" in codigo
    assert "char_length(nome_cliente_assinatura) > 100" in codigo
    assert codigo.index("char_length") < primeiro_alter
    # volta aos tipos originais (0000_inventario.sql): 100 / 20 / 100
    assert re.search(r"contato_principal_nome\s+TYPE varchar\(100\)", codigo)
    assert re.search(r"contato_principal_telefone\s+TYPE varchar\(20\)", codigo)
    assert re.search(r"nome_cliente_assinatura TYPE varchar\(100\)", codigo)
    assert codigo.count("RAISE EXCEPTION") == 2 and "BEGIN;" in codigo and codigo.rstrip().endswith("COMMIT;")


def test_consultas_de_conferencia_e_readme_da_0014():
    consultas = _sql("0014_consultas_conferencia.sql")
    for rotulo in ("B1.", "B2.", "B3."):
        assert rotulo in consultas
    assert re.findall(r"^(?:INSERT|UPDATE|DELETE|ALTER|DROP)\b", _sem_comentarios(consultas), re.M | re.I) == []  # so leitura
    readme = (BACKEND / "migrations" / "README.md").read_text(encoding="utf-8")
    linha = next(l for l in readme.splitlines() if l.startswith("| 14 |"))
    # O status (NAO APLICADA -> APLICADA em 12/11/2026) muda com a janela de execucao; o teste so exige que a linha
    # registre o estado e continue apontando para o rollback e para o --verificar.
    assert re.search(r"\bAPLICADA\b", linha) and "0014_rollback.sql" in linha and "--verificar" in linha


def test_limite_sqlite_nao_aplica_varchar_n_entao_o_estouro_de_varchar_nao_e_verificavel_aqui():
    """REGISTRO: o SQLite ignora o tamanho de VARCHAR(n). Por isso nenhum teste desta suite prova que a 0014 e necessaria
    (sem ela, enc1:... estoura varchar(100)/(20) no PostgreSQL). Prova so possivel contra PostgreSQL."""
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE t (v VARCHAR(5))"))
        c.execute(text("INSERT INTO t VALUES (:v)"), {"v": "x" * 500})
        assert len(c.execute(text("SELECT v FROM t")).scalar()) == 500  # aceito: SQLite nao aplica o limite
    assert len(crypto.cifrar("x" * 100, "cliente.contato_principal_nome")) > 100  # e o cifrado de 100 chars nao cabe em 100


# =====================================================================================================================
# CA-V07-9: guarda do ambiente de teste
# =====================================================================================================================

def test_ca_v07_9_a_suite_roda_em_sqlite_temporario_com_o_modo_legado_desligado():
    assert engine.url.get_backend_name() == "sqlite"
    assert config.ENCRYPTION_ALLOW_LEGACY_PLAINTEXT is False
    assert config.STORAGE_BACKEND == "local" and not config.SUPABASE_URL
