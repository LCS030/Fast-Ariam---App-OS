#!/usr/bin/env python
"""
Smoke test ponta a ponta da API Fast Ariam (SDD v0.5, secoes 5, 6.5 a 6.13, 10 e 11/11.1) via HTTP.

ATENCAO: este script ESCREVE no banco da API alvo. Em dev (= producao no mesmo Supabase) isso e o banco REAL.
Confira a linha "alvo:" impressa no inicio e leia backend/ROTEIRO_TESTE_API.md (riscos e limpeza) antes de rodar.

NAO usa o banco diretamente: tudo passa pela API em BASE_URL. Cria dados de teste (cliente, tecnicos, modelos de
equipamento, OS) com o prefixo "TESTE-SMOKE-" para facilitar a limpeza, e NAO apaga nada (imprime um SQL de limpeza
apenas como sugestao).

Regras da v0.5 exercitadas (resumo):
  * catalogo de modelos (admin) e OS SEMPRE com equipamentos[] (422 sem eles); o tecnico nao cria/edita equipamento;
  * o servidor cria um registro de servico por equipamento em cada visita (POST .../servicos = 410; o tecnico faz PATCH);
  * atendimento so inicia com foto de defeito de CADA equipamento (409) e so finaliza com "salvar conserto" + foto de
    conserto de cada equipamento (409); a cada visita as exigencias recomecam;
  * admin edita equipamento so ate o inicio do atendimento; OS Finalizada: admin corrige apenas fotos e materiais
    (custo RECALCULADO com os valores congelados; modelo/serie travados);
  * sincronizacao offline: /api/sync/arquivos, /api/sync/eventos e /api/sync/minhas-os.

Variaveis de ambiente:
  BASE_URL        padrao http://127.0.0.1:8000   (o prefixo /api e acrescentado pelo script)
  ADMIN_EMAIL     e-mail de um administrador ATIVO (obrigatoria)
  ADMIN_PASSWORD  senha desse administrador (obrigatoria)
  SMOKE_SKIP_BIG_UPLOAD=1   (opcional) pula o upload de ~15 MB (conexoes lentas)
  SMOKE_TIMEOUT   (opcional) timeout por requisicao em segundos (padrao 60)

Saida: uma linha por passo (OK / FALHA), resumo no fim e codigo de saida 0 (tudo certo), 1 (alguma falha) ou
2 (configuracao invalida / API inacessivel / login admin falhou).

Dependencias: httpx e Pillow (ambas ja estao em requirements.txt).

Exemplo (PowerShell):
  $env:BASE_URL="http://127.0.0.1:8000"; $env:ADMIN_EMAIL="admin@exemplo.com"; $env:ADMIN_PASSWORD="..."
  python scripts/smoke_api.py
"""
from __future__ import annotations

import hashlib
import os
import random
import secrets
import string
import sys
import traceback
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import httpx
from PIL import Image

try:  # console do Windows (cp1252) nao imprime os simbolos; forca UTF-8 quando possivel
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # pragma: no cover
    pass

OK = "✔"
KO = "✘"
SKIP = "-"

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
TIMEOUT = float(os.getenv("SMOKE_TIMEOUT", "60"))
SKIP_BIG = os.getenv("SMOKE_SKIP_BIG_UPLOAD", "").strip().lower() in ("1", "true", "yes", "sim")

if BASE_URL.endswith("/api"):
    BASE_URL = BASE_URL[:-4]
API = BASE_URL + "/api"

RUN_ID = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
PREFIXO = "TESTE-SMOKE-"
SENHA_TECNICO = "Smk#" + secrets.token_urlsafe(12)  # aleatoria por execucao; nunca impressa (contas de teste ficam ativas ate a limpeza)

# Fuso de negocio do servidor (America/Sao_Paulo = UTC-3, sem horario de verao desde 2019).
HOJE = datetime.now(timezone(timedelta(hours=-3))).date()


# =====================================================================================================================
# Infra: contadores, saida e HTTP
# =====================================================================================================================

class Placar:
    def __init__(self) -> None:
        self.ok = 0
        self.falhas: List[str] = []
        self.pulados: List[str] = []
        self.cenario = "setup"
        self.por_cenario: Dict[str, List[int]] = {}

    def _contar(self, idx: int) -> None:
        self.por_cenario.setdefault(self.cenario, [0, 0, 0])[idx] += 1

    def passou(self, desc: str) -> None:
        self.ok += 1
        self._contar(0)
        print(f"  {OK} {desc}")

    def falhou(self, desc: str, detalhe: str = "") -> None:
        self.falhas.append(f"[{self.cenario}] {desc}" + (f" -> {detalhe}" if detalhe else ""))
        self._contar(1)
        print(f"  {KO} {desc}" + (f"\n      {detalhe}" if detalhe else ""))

    def pulou(self, desc: str, motivo: str) -> None:
        self.pulados.append(f"[{self.cenario}] {desc} ({motivo})")
        self._contar(2)
        print(f"  {SKIP} (pulado) {desc}: {motivo}")


P = Placar()
client = httpx.Client(base_url=API, timeout=TIMEOUT)

# IDs criados (para o relatorio final e o SQL de limpeza sugerido)
CRIADOS: Dict[str, List[int]] = {"clientes": [], "tecnicos": [], "os": [], "modelos": []}


class Resp:
    """Resposta tolerante: erro de rede vira status 0, para o passo falhar em vez de derrubar o cenario."""

    def __init__(self, r: Optional[httpx.Response], erro: str = "") -> None:
        self.r = r
        self.erro = erro
        self.status_code = r.status_code if r is not None else 0

    @property
    def text(self) -> str:
        return self.r.text if self.r is not None else self.erro

    def json(self) -> Any:
        try:
            return self.r.json() if self.r is not None else {}
        except Exception:
            return {}

    def resumo(self) -> str:
        t = (self.text or "").replace("\n", " ")
        return f"HTTP {self.status_code}: {t[:260]}"


def http(method: str, path: str, token: Optional[str] = None, **kw: Any) -> Resp:
    headers = dict(kw.pop("headers", {}) or {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    arquivos = kw.get("files")
    if isinstance(arquivos, dict) and isinstance(arquivos.get("file"), tuple):
        # SHA256_ORIGEM_OBRIGATORIO=true: todo upload leva o SHA-256 dos bytes (como faz o app).
        dados = dict(kw.get("data") or {})
        dados.setdefault("sha256", hashlib.sha256(arquivos["file"][1]).hexdigest())
        kw["data"] = dados
    try:
        return Resp(client.request(method, path, headers=headers, **kw))
    except httpx.HTTPError as exc:
        return Resp(None, f"{type(exc).__name__}: {exc}")


Codes = Union[int, Sequence[int]]


def _lista(c: Codes) -> Tuple[int, ...]:
    return (c,) if isinstance(c, int) else tuple(c)


def expect(desc: str, resp: Resp, codes: Codes, quiet: bool = False) -> Resp:
    """Registra o passo. quiet=True: so imprime/conta quando FALHA (passos de preparacao)."""
    if resp.status_code in _lista(codes):
        if not quiet:
            P.passou(f"{desc} [{resp.status_code}]")
    else:
        P.falhou(desc, f"esperado {'/'.join(map(str, _lista(codes)))}, obtido {resp.resumo()}")
    return resp


def verifica(desc: str, cond: bool, detalhe: str = "", quiet: bool = False) -> bool:
    if cond:
        if not quiet:
            P.passou(desc)
    else:
        P.falhou(desc, detalhe)
    return bool(cond)


def etapa(titulo: str) -> None:
    print(f"\n=== {titulo} ===")


# =====================================================================================================================
# Geradores de dados
# =====================================================================================================================

def gerar_cpf() -> str:
    while True:
        base = [random.randint(0, 9) for _ in range(9)]
        if len(set(base)) == 1:
            continue
        for tam in (9, 10):
            soma = sum(base[i] * (tam + 1 - i) for i in range(tam))
            base.append((soma * 10) % 11 % 10)
        return "".join(map(str, base))


def gerar_cnpj() -> str:
    while True:
        base = [random.randint(0, 9) for _ in range(12)]
        if len(set(base)) == 1:
            continue
        for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
            soma = sum(base[i] * pesos[i] for i in range(len(pesos)))
            resto = soma % 11
            base.append(0 if resto < 2 else 11 - resto)
        return "".join(map(str, base))


def jpeg(largura: int, altura: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (largura, altura), color=(200, 40, 40)).save(buf, format="JPEG", quality=60)
    return buf.getvalue()


def png(largura: int, altura: int) -> bytes:
    buf = BytesIO()
    Image.new("RGB", (largura, altura), color=(30, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def gif() -> bytes:
    buf = BytesIO()
    Image.new("P", (50, 50)).save(buf, format="GIF")
    return buf.getvalue()


def assinatura_b64() -> str:
    import base64
    return "data:image/png;base64," + base64.b64encode(png(200, 80)).decode()


def arq_jpeg(nome: str = "foto.jpg", w: int = 200, h: int = 150) -> Dict[str, Any]:
    return {"file": (nome, jpeg(w, h), "image/jpeg")}


def arq_conserto(nome: str = "conserto.jpg") -> Dict[str, Any]:
    return {"file": (nome, jpeg(960, 1280), "image/jpeg")}


CPF_CLIENTE_VALIDO = "529.982.247-25"
CPF_CLIENTE_INVALIDO = "111.111.111-11"


# =====================================================================================================================
# Operacoes de apoio (cadastros e etapas do fluxo)
# =====================================================================================================================

class Tecnico:
    def __init__(self, id_: int, email: str) -> None:
        self.id = id_
        self.email = email
        self.token: Optional[str] = None


ADMIN_TOKEN: Optional[str] = None
ADMIN_ID: Optional[int] = None


def login(email: str, senha: str) -> Resp:
    return http("POST", "/auth/login", data={"username": email, "password": senha})


def login_tecnico(t: Tecnico) -> Optional[str]:
    r = login(t.email, SENHA_TECNICO)
    if r.status_code == 200:
        t.token = r.json().get("access_token")
    return t.token


def novo_cliente(rotulo: str = "") -> Optional[int]:
    codigo = random.randint(1_500_000_000, 2_100_000_000)
    r = http("POST", "/clientes/", ADMIN_TOKEN, json={
        "razao_social": f"{PREFIXO}CLIENTE{rotulo}-{RUN_ID}", "telefone": "2733334444",
        "endereco": "RUA DOS TESTES", "numero": "100", "bairro": "CENTRO", "cidade": "SERRA", "uf": "ES",
        "codigo": codigo, "contato_principal_nome": "Contato Smoke", "contato_principal_telefone": "27999990000"})
    if r.status_code == 201:
        cid = r.json()["id_cliente"]
        CRIADOS["clientes"].append(cid)
        return cid
    P.falhou(f"criar cliente de apoio{rotulo}", r.resumo())
    return None


def novo_tecnico(rotulo: str, quiet: bool = True) -> Optional[Tecnico]:
    suf = f"{rotulo}-{RUN_ID}-{random.randint(100, 999)}"
    email = f"teste-smoke-{suf}@exemplo.com.br".lower()
    r = http("POST", "/tecnicos/", ADMIN_TOKEN, json={
        "nome": f"{PREFIXO}{suf}", "cnpj": gerar_cnpj(), "cpf": gerar_cpf(), "inscricao_estadual": "ISENTO",
        "email": email, "telefone": "(27) 99999-0000", "password": SENHA_TECNICO, "role": "tecnico",
        "is_active": True, "dados_bancarios": {"banco": "Banco Teste", "agencia": "0001", "conta": "12345-6",
                                               "pix": email}})
    if not quiet:
        expect(f"criar tecnico de teste ({rotulo})", r, 201)
    if r.status_code != 201:
        if quiet:
            P.falhou(f"criar tecnico de apoio ({rotulo})", r.resumo())
        return None
    d = r.json()
    CRIADOS["tecnicos"].append(d["id_tecnico"])
    if not quiet:
        verifica("tecnico: CPF devolvido com mascara (14 chars) e CNPJ com mascara (18 chars)",
                 len(d.get("cpf", "")) == 14 and len(d.get("cnpj", "")) == 18, f"cpf={d.get('cpf')} cnpj={d.get('cnpj')}")
        verifica("tecnico: resposta nao expoe password/password_hash",
                 "password" not in d and "password_hash" not in d)
    t = Tecnico(d["id_tecnico"], d["email"])
    if not login_tecnico(t):
        P.falhou(f"login do tecnico de teste ({rotulo})")
        return None
    return t


def novo_modelo(rotulo: str, quiet: bool = True) -> Optional[int]:
    """Modelo no catalogo de equipamentos (admin). Nome unico por execucao, com o prefixo de teste."""
    r = http("POST", "/equipamentos/", ADMIN_TOKEN, json={"modelo": f"{PREFIXO}MODELO-{rotulo}-{RUN_ID}"})
    if not quiet:
        expect(f"criar modelo de equipamento ({rotulo})", r, 201)
    if r.status_code == 201:
        mid = r.json()["id_equipamento_modelo"]
        CRIADOS["modelos"].append(mid)
        return mid
    if quiet:
        P.falhou(f"criar modelo de apoio ({rotulo})", r.resumo())
    return None


_serie_seq = [0]


def equipamentos(n: int = 1, modelo_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """`n` equipamentos (modelo + numero de serie unico) no formato de ChamadoCreate.equipamentos."""
    mid = modelo_id if modelo_id is not None else Ctx.modelo_id
    itens = []
    for _ in range(n):
        _serie_seq[0] += 1
        itens.append({"id_equipamento_modelo": mid, "numero_serie": f"SMK-{RUN_ID}-{_serie_seq[0]:03d}"})
    return itens


def nova_os(cliente_id: int, tecnico_id: Optional[int] = None, rotulo: str = "", quiet: bool = True,
            data_agendamento: Optional[date] = None, n_equip: int = 1,
            equips: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    if Ctx.modelo_id is None and equips is None:
        P.falhou(f"criar OS ({rotulo})", "nao ha modelo de equipamento de teste (catalogo falhou)")
        return None
    corpo: Dict[str, Any] = {"id_cliente": cliente_id,
                             "descricao_cliente": f"{PREFIXO}{RUN_ID} {rotulo} - gondola sem refrigeracao",
                             "pedido": f"PED-SMOKE-{RUN_ID}", "em_garantia": True,
                             "equipamentos": equips if equips is not None else equipamentos(n_equip)}
    if tecnico_id is not None:
        corpo["id_tecnico_atribuido"] = tecnico_id
    if data_agendamento is not None:
        corpo["data_agendamento"] = data_agendamento.isoformat()
    r = http("POST", "/chamados/", ADMIN_TOKEN, json=corpo)
    if r.status_code != 201:
        P.falhou(f"criar OS ({rotulo})", r.resumo())
        return None
    d = r.json()
    CRIADOS["os"].append(d["id_os"])
    return d


def get_os(os_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    return http("GET", f"/chamados/{os_id}", token or ADMIN_TOKEN).json()


def visita_atual(os_id: int) -> Optional[int]:
    visitas = get_os(os_id).get("visitas") or []
    return max((v["id_visita"] for v in visitas), default=None)


def pre(desc: str, resp: Resp, codes: Codes = 200) -> bool:
    """Passo de preparacao: silencioso quando OK; falha registrada se nao for o esperado."""
    return expect(desc, resp, codes, quiet=True).status_code in _lista(codes)


def base(os_id: int, vid: int) -> str:
    return f"/chamados/{os_id}/visitas/{vid}"


def servicos_da_visita(os_id: int, vid: int, token: Optional[str] = None) -> List[Dict[str, Any]]:
    r = http("GET", base(os_id, vid) + "/servicos", token or ADMIN_TOKEN)
    d = r.json()
    return d if isinstance(d, list) else []


def estado_da_visita(os_id: int, vid: int, token: str) -> Dict[str, Any]:
    return http("GET", base(os_id, vid) + "/estado", token).json()


def ida_completa(os_id: int, vid: int, token: str, km0: int = 1000, quiet: bool = True) -> bool:
    ok = expect("iniciar deslocamento de ida", http("POST", base(os_id, vid) + "/iniciar-deslocamento", token,
                json={"tipo": "ida", "km_inicio": km0}), 200, quiet).status_code == 200
    ok &= expect("upload da foto de inicio da ida", http("POST", base(os_id, vid) + "/upload-deslocamento", token,
                 files=arq_jpeg(), data={"tipo": "ida", "momento": "inicio"}), 200, quiet).status_code == 200
    ok &= expect("finalizar deslocamento de ida", http("POST", base(os_id, vid) + "/finalizar-deslocamento", token,
                 json={"tipo": "ida", "km_fim": km0 + 20}), 200, quiet).status_code == 200
    return ok


def fotos_defeito_todas(os_id: int, vid: int, token: str, quiet: bool = True) -> bool:
    """Foto de defeito de CADA equipamento (pre-condicao de iniciar o atendimento, TR-12). Foto pequena vale."""
    servicos = servicos_da_visita(os_id, vid, token)
    ok = bool(servicos)
    for s in servicos:
        ok &= expect(f"foto de defeito do equipamento {s.get('numero_serie')}", http(
            "POST", base(os_id, vid) + f"/servicos/{s['id_servico']}/upload-foto", token, files=arq_jpeg("defeito.jpg"),
            data={"tipo": "defeito"}), 200, quiet).status_code == 200
    return ok


def iniciar_atendimento(os_id: int, vid: int, token: str, quiet: bool = True, com_fotos: bool = True) -> bool:
    if com_fotos and not fotos_defeito_todas(os_id, vid, token):
        return False
    return expect("iniciar atendimento", http("POST", base(os_id, vid) + "/iniciar-atendimento", token),
                  200, quiet).status_code == 200


def volta_completa(os_id: int, vid: int, token: str, km0: int = 1020, quiet: bool = True) -> Resp:
    expect("iniciar deslocamento de volta", http("POST", base(os_id, vid) + "/iniciar-deslocamento", token,
           json={"tipo": "volta", "km_inicio": km0}), 200, quiet)
    expect("upload da foto de inicio da volta", http("POST", base(os_id, vid) + "/upload-deslocamento", token,
           files=arq_jpeg(), data={"tipo": "volta", "momento": "inicio"}), 200, quiet)
    expect("upload da foto de fim da volta (odometro final)", http("POST", base(os_id, vid) + "/upload-deslocamento",
           token, files=arq_jpeg(), data={"tipo": "volta", "momento": "fim"}), 200, quiet)
    return expect("finalizar deslocamento de volta", http("POST", base(os_id, vid) + "/finalizar-deslocamento", token,
                  json={"tipo": "volta", "km_fim": km0 + 20}), 200, quiet)


# PATCH do servico pelo tecnico (SDD 6.7.1, v0.5): so defeitos, descricoes e materiais; NUNCA serie/nome/equipamento.
MATERIAL_A = {"nome": "Compressor 1/4 HP", "quantidade": 1, "valor": 850.00}
MATERIAL_B = {"nome": "Filtro secador", "quantidade": 2, "valor": 15.00}
PATCH_SERVICO_A = {
    "defeitos_principais": ["Refrigeração"], "sub_defeitos_refrigeracao": ["Compressor"],
    "sub_defeitos_compressor": ["Queimado"], "sub_defeitos_vazamento": [], "vazamento_ponto_descricao": None,
    "sub_defeitos_outros": [], "sub_defeitos_iluminacao": [], "sub_defeitos_estrutura": [],
    "defeito_outros_descricao": None, "materiais_utilizados": [MATERIAL_A],
}
PATCH_SERVICO_B = {"defeitos_principais": ["Refrigeração"], "materiais_utilizados": [MATERIAL_B]}


def conserto_completo(os_id: int, vid: int, token: str, quiet: bool = True) -> bool:
    """Defeito + materiais + "Salvar conserto" + foto de conserto (960x1280) de CADA equipamento (TR-13)."""
    servicos = servicos_da_visita(os_id, vid, token)
    ok = bool(servicos)
    for i, s in enumerate(servicos):
        sb = base(os_id, vid) + f"/servicos/{s['id_servico']}"
        corpo = PATCH_SERVICO_A if i == 0 else PATCH_SERVICO_B
        ok &= expect(f"preencher servico do equipamento {s.get('numero_serie')}",
                     http("PATCH", sb, token, json=corpo), 200, quiet).status_code == 200
        ok &= expect(f"salvar conserto do equipamento {s.get('numero_serie')}",
                     http("POST", sb + "/salvar-conserto", token, json={}), 200, quiet).status_code == 200
        ok &= expect(f"foto de conserto do equipamento {s.get('numero_serie')}",
                     http("POST", sb + "/upload-foto", token, files=arq_conserto(), data={"tipo": "conserto"}),
                     200, quiet).status_code == 200
    return ok


def finalizar_atendimento(os_id: int, vid: int, token: str, quiet: bool = True) -> bool:
    return expect("finalizar atendimento (CPF valido + assinatura)", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", token,
        json={"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO,
              "assinatura_base64": assinatura_b64()}), 200, quiet).status_code == 200


def fluxo_ate_atendimento(os_id: int, tok: str) -> Optional[int]:
    """Ida completa + foto de defeito de cada equipamento + atendimento iniciado. Retorna o id da visita."""
    vid = visita_atual(os_id)
    if vid is None:
        P.falhou(f"OS {os_id} sem visita para executar o fluxo")
        return None
    if ida_completa(os_id, vid, tok) and iniciar_atendimento(os_id, vid, tok):
        return vid
    return None


def fluxo_completo(os_id: int, tok: str) -> bool:
    """Fluxo normal inteiro, em silencio (so falhas aparecem). Termina com a OS Finalizado."""
    vid = fluxo_ate_atendimento(os_id, tok)
    if vid is None:
        return False
    if not conserto_completo(os_id, vid, tok) or not finalizar_atendimento(os_id, vid, tok):
        return False
    r = volta_completa(os_id, vid, tok)
    return r.status_code == 200 and get_os(os_id).get("status") == "Finalizado"


def custos(os_id: int, token: Optional[str] = None) -> Dict[str, Any]:
    return http("GET", f"/chamados/{os_id}/custos", token or ADMIN_TOKEN).json()


# =====================================================================================================================
# Estado compartilhado entre cenarios (cada cenario degrada com "pulado" se a dependencia faltar)
# =====================================================================================================================

class Ctx:
    cliente_id: Optional[int] = None
    tec1: Optional[Tecnico] = None
    modelo_id: Optional[int] = None          # modelo ativo do catalogo usado nas OS de teste
    modelo2_id: Optional[int] = None         # segundo modelo (troca de modelo na edicao do admin)
    os_final: Optional[int] = None           # OS finalizada no cenario 1 (2 equipamentos)
    os_final_vid: Optional[int] = None
    os_final_servicos: List[int] = []        # ids de servico da OS finalizada (1 por equipamento)
    os_final_materiais: Optional[float] = None  # custo_total_materiais congelado esperado da OS finalizada


# =====================================================================================================================
# a) Autenticacao
# =====================================================================================================================

def cenario_a_autenticacao() -> None:
    global ADMIN_TOKEN, ADMIN_ID
    r = expect("login do admin", login(ADMIN_EMAIL, ADMIN_PASSWORD), 200)
    if r.status_code != 200 or not r.json().get("access_token"):
        raise SystemExit(_abortar("login do administrador falhou; confira ADMIN_EMAIL/ADMIN_PASSWORD e se o usuario esta ativo"))
    ADMIN_TOKEN = r.json()["access_token"]
    verifica("token_type = bearer", r.json().get("token_type") == "bearer")

    me = expect("GET /auth/me com token valido", http("GET", "/auth/me", ADMIN_TOKEN), 200)
    d = me.json()
    verifica("/auth/me devolve role=admin e e-mail do login",
             d.get("role") == "admin" and (d.get("email") or "").lower() == ADMIN_EMAIL.lower(), str(d))
    verifica("/auth/me nao expoe dados bancarios, CPF, CNPJ nem telefone",
             not any(k in d for k in ("cpf", "cnpj", "telefone", "banco", "dados_bancarios", "password_hash")), str(list(d)))
    ADMIN_ID = d.get("id_tecnico")

    expect("GET /auth/me com token invalido -> 401", http("GET", "/auth/me", "token.invalido.xyz"), 401)
    expect("GET /auth/me sem token -> 401", http("GET", "/auth/me"), 401)
    expect("login com senha errada -> 401 (mensagem unica)", login(ADMIN_EMAIL, ADMIN_PASSWORD + "x"), 401)


def _abortar(msg: str) -> int:
    print(f"\nABORTADO: {msg}")
    return 2


# =====================================================================================================================
# b) Cadastros base (cliente, tecnico) e catalogo de modelos de equipamento
# =====================================================================================================================

def cenario_b_cadastros() -> None:
    cid = novo_cliente()
    verifica("cliente de teste criado (codigo unico aleatorio)", cid is not None)
    Ctx.cliente_id = cid
    if cid is not None:
        r = http("POST", "/clientes/", ADMIN_TOKEN, json={
            "razao_social": f"{PREFIXO}SEM-CODIGO", "telefone": "2733334444", "endereco": "RUA X", "numero": "1",
            "bairro": "CENTRO", "cidade": "SERRA", "uf": "ES"})
        expect("criar cliente sem 'codigo' -> 422 (e nao 500)", r, 422)
        c = http("GET", f"/clientes/{cid}", ADMIN_TOKEN)
        expect("GET /clientes/{id} como admin", c, 200)

    Ctx.tec1 = novo_tecnico("tec1", quiet=False)
    if Ctx.tec1 is not None:
        r = http("POST", "/tecnicos/", ADMIN_TOKEN, json={
            "nome": f"{PREFIXO}senha-curta", "cnpj": gerar_cnpj(), "cpf": gerar_cpf(), "email": f"teste-smoke-sc-{RUN_ID}@exemplo.com.br",
            "telefone": "27999990000", "password": "curta",
            "dados_bancarios": {"banco": "B", "agencia": "1", "conta": "2"}})
        expect("criar tecnico com senha < 8 -> 422", r, 422)
        r = http("POST", "/tecnicos/", ADMIN_TOKEN, json={
            "nome": f"{PREFIXO}cpf-invalido", "cnpj": gerar_cnpj(), "cpf": "111.111.111-11",
            "email": f"teste-smoke-ci-{RUN_ID}@exemplo.com.br", "telefone": "27999990000", "password": SENHA_TECNICO,
            "dados_bancarios": {"banco": "B", "agencia": "1", "conta": "2"}})
        expect("criar tecnico com CPF invalido -> 422", r, 422)

    # --- catalogo de modelos (SDD 6.13, RN-40): so o admin; nome unico sem diferenciar maiusculas/espacos ---
    Ctx.modelo_id = novo_modelo("A", quiet=False)
    Ctx.modelo2_id = novo_modelo("B", quiet=False)
    if Ctx.modelo_id is None:
        P.pulou("verificacoes do catalogo", "modelo de teste nao foi criado")
        return
    nome_a = f"{PREFIXO}MODELO-A-{RUN_ID}"
    mid = Ctx.modelo_id
    r = http("GET", f"/equipamentos/{mid}", ADMIN_TOKEN)
    expect("GET /equipamentos/{id} como admin", r, 200)
    verifica("modelo criado ativo e com o nome informado", r.json().get("is_active") is True
             and r.json().get("modelo") == nome_a, str(r.json()))
    expect("criar modelo com nome so de espacos -> 422", http("POST", "/equipamentos/", ADMIN_TOKEN,
           json={"modelo": "   "}), 422)
    expect("criar modelo sem corpo -> 422", http("POST", "/equipamentos/", ADMIN_TOKEN, json={}), 422)
    expect("criar modelo duplicado (minusculas) -> 409", http("POST", "/equipamentos/", ADMIN_TOKEN,
           json={"modelo": nome_a.lower()}), 409)
    expect("criar modelo duplicado (maiusculas e espacos nas pontas) -> 409", http(
        "POST", "/equipamentos/", ADMIN_TOKEN, json={"modelo": f"  {nome_a.upper()}  "}), 409)
    expect("GET /equipamentos/{id} inexistente -> 404", http("GET", "/equipamentos/2147000000", ADMIN_TOKEN), 404)
    lista = http("GET", "/equipamentos/", ADMIN_TOKEN).json()
    verifica("GET /equipamentos/ (admin) lista o modelo criado",
             isinstance(lista, list) and mid in [m["id_equipamento_modelo"] for m in lista])
    if Ctx.tec1 is not None and Ctx.tec1.token:
        t1 = Ctx.tec1.token
        expect("tecnico POST /equipamentos -> 403", http("POST", "/equipamentos/", t1, json={"modelo": "X"}), 403)
        expect("tecnico GET /equipamentos -> 403", http("GET", "/equipamentos/", t1), 403)
        expect("tecnico PATCH /equipamentos/{id} -> 403", http("PATCH", f"/equipamentos/{mid}", t1,
               json={"modelo": "Y"}), 403)
        expect("tecnico DELETE /equipamentos/{id} -> 403", http("DELETE", f"/equipamentos/{mid}", t1), 403)
    if Ctx.modelo2_id is not None:
        expect("renomear o modelo B para o nome do A (ignora maiusculas) -> 409", http(
            "PATCH", f"/equipamentos/{Ctx.modelo2_id}", ADMIN_TOKEN, json={"modelo": nome_a.lower()}), 409)
        novo_nome = f"{PREFIXO}MODELO-B-RENOMEADO-{RUN_ID}"
        r = expect("renomear o modelo B para um nome livre -> 200", http(
            "PATCH", f"/equipamentos/{Ctx.modelo2_id}", ADMIN_TOKEN, json={"modelo": novo_nome}), 200)
        verifica("nome do modelo B atualizado", r.json().get("modelo") == novo_nome, str(r.json()))

    # desativacao logica: nunca exclui, so impede NOVOS vinculos (T-39)
    mc = novo_modelo("C-desativavel")
    if mc is not None and Ctx.cliente_id is not None:
        expect("desativar o modelo C (DELETE = desativacao logica) -> 204", http("DELETE", f"/equipamentos/{mc}", ADMIN_TOKEN), 204)
        verifica("modelo C continua listado, mas inativo", http("GET", f"/equipamentos/{mc}", ADMIN_TOKEN).json()
                 .get("is_active") is False)
        expect("criar OS com modelo INATIVO -> 422", http("POST", "/chamados/", ADMIN_TOKEN, json={
            "id_cliente": Ctx.cliente_id, "descricao_cliente": f"{PREFIXO}modelo inativo",
            "equipamentos": [{"id_equipamento_modelo": mc, "numero_serie": f"INA-{RUN_ID}"}]}), 422)
        expect("reativar o modelo C -> 200", http("PATCH", f"/equipamentos/{mc}", ADMIN_TOKEN,
               json={"is_active": True}), 200)


# =====================================================================================================================
# c) Cenario 1 - fluxo normal (2 equipamentos)
# =====================================================================================================================

def cenario_1_fluxo_normal() -> None:
    if Ctx.cliente_id is None or Ctx.tec1 is None or not Ctx.tec1.token or Ctx.modelo_id is None:
        P.pulou("cenario 1", "cliente/tecnico/modelo de teste nao foram criados")
        return
    tec, tok = Ctx.tec1, Ctx.tec1.token

    # --- OS so e criada COM equipamentos (RN-41) ---
    corpo_base = {"id_cliente": Ctx.cliente_id, "descricao_cliente": f"{PREFIXO}{RUN_ID} sem equipamento"}
    expect("criar OS SEM o campo equipamentos -> 422", http("POST", "/chamados/", ADMIN_TOKEN, json=corpo_base), 422)
    expect("criar OS com equipamentos=[] -> 422", http("POST", "/chamados/", ADMIN_TOKEN,
           json={**corpo_base, "equipamentos": []}), 422)
    expect("criar OS com modelo inexistente -> 422", http("POST", "/chamados/", ADMIN_TOKEN, json={
        **corpo_base, "equipamentos": [{"id_equipamento_modelo": 2147000000, "numero_serie": "X-1"}]}), 422)
    expect("criar OS com numero de serie em branco -> 422", http("POST", "/chamados/", ADMIN_TOKEN, json={
        **corpo_base, "equipamentos": [{"id_equipamento_modelo": Ctx.modelo_id, "numero_serie": "   "}]}), 422)
    expect("criar OS com serie repetida na lista (ignora maiusculas) -> 422", http("POST", "/chamados/", ADMIN_TOKEN, json={
        **corpo_base, "equipamentos": [{"id_equipamento_modelo": Ctx.modelo_id, "numero_serie": f"dup-{RUN_ID}"},
                                       {"id_equipamento_modelo": Ctx.modelo_id, "numero_serie": f"DUP-{RUN_ID}"}]}), 422)

    os_ = nova_os(Ctx.cliente_id, None, "cenario1", n_equip=2)
    if not verifica("criar OS sem tecnico, com 2 equipamentos -> 201", os_ is not None):
        return
    os_id = os_["id_os"]
    verifica("OS sem tecnico nasce 'Pendente' sem tecnico e sem visita",
             os_["status"] == "Pendente" and os_["id_tecnico_atribuido"] is None and not os_.get("visitas"),
             f"status={os_['status']} visitas={len(os_.get('visitas') or [])}")
    eqs = os_.get("equipamentos") or []
    verifica("resposta traz os 2 equipamentos (modelo + serie)", len(eqs) == 2 and all(
        e.get("modelo") and e.get("numero_serie") and e.get("id_os_equipamento") for e in eqs), str(eqs))

    r = expect("atribuir tecnico (PATCH so com id_tecnico_atribuido)", http(
        "PATCH", f"/chamados/{os_id}", ADMIN_TOKEN, json={"id_tecnico_atribuido": tec.id}), 200)
    d = r.json()
    verifica("OS passou a 'Agendado' e ja traz exatamente 1 visita (RN-11a)",
             d.get("status") == "Agendado" and len(d.get("visitas") or []) == 1,
             f"status={d.get('status')} visitas={len(d.get('visitas') or [])}")
    if d.get("status") != "Agendado" or not d.get("visitas"):
        return
    vid = d["visitas"][0]["id_visita"]
    verifica("visita automatica ainda nao finalizada", d["visitas"][0]["servico_finalizado"] is False)
    sv = servicos_da_visita(os_id, vid, tok)
    verifica("o servidor criou 1 registro de servico por equipamento (2), sem conserto salvo e sem legado",
             len(sv) == 2 and all(s.get("is_legado") is False and s.get("conserto_salvo_em") is None for s in sv),
             str(sv)[:300])
    verifica("registros de servico trazem modelo e serie (somente leitura) iguais aos da OS",
             sorted(s.get("numero_serie") for s in sv) == sorted(e["numero_serie"] for e in eqs), str(sv)[:300])
    if len(sv) != 2:
        return

    # --- tecnico NAO cria/edita equipamento (RN-42) ---
    expect("tecnico POST .../servicos (descontinuado) -> 410", http(
        "POST", base(os_id, vid) + "/servicos", tok, json={"numero_serie_atendido": "SN", "nome_equipamento": "X"}), 410)
    expect("tecnico POST /chamados/{os}/equipamentos -> 403", http(
        "POST", f"/chamados/{os_id}/equipamentos", tok,
        json={"id_equipamento_modelo": Ctx.modelo_id, "numero_serie": f"TEC-{RUN_ID}"}), 403)
    expect("tecnico PATCH /chamados/{os}/equipamentos/{id} -> 403", http(
        "PATCH", f"/chamados/{os_id}/equipamentos/{eqs[0]['id_os_equipamento']}", tok, json={"numero_serie": "HACK"}), 403)
    expect("tecnico DELETE /chamados/{os}/equipamentos/{id} -> 403", http(
        "DELETE", f"/chamados/{os_id}/equipamentos/{eqs[0]['id_os_equipamento']}", tok), 403)
    le = http("GET", f"/chamados/{os_id}/equipamentos", tok)
    expect("tecnico atribuido LE os equipamentos da OS (somente leitura)", le, 200)
    verifica("leitura traz so id_os_equipamento, id_equipamento_modelo, modelo e numero_serie",
             isinstance(le.json(), list) and len(le.json()) == 2
             and set(le.json()[0]) == {"id_os_equipamento", "id_equipamento_modelo", "modelo", "numero_serie"}, le.text[:200])
    s0 = base(os_id, vid) + f"/servicos/{sv[0]['id_servico']}"
    for campo, valor in (("numero_serie_atendido", "HACK"), ("nome_equipamento", "Outro"), ("numero_serie", "HACK"),
                         ("modelo", "Outro"), ("id_os_equipamento", 999)):
        expect(f"PATCH do servico com '{campo}' -> 422 (tecnico nao informa equipamento/serie)", http(
            "PATCH", s0, tok, json={campo: valor}), 422)

    lista = expect("tecnico lista /chamados", http("GET", "/chamados/", tok), 200).json()
    verifica("lista do tecnico contem a OS e SOMENTE OS dele",
             isinstance(lista, list) and os_id in [o["id_os"] for o in lista]
             and all(o["id_tecnico_atribuido"] == tec.id for o in lista),
             f"ids={[ (o['id_os'], o['id_tecnico_atribuido']) for o in lista][:5]}")
    expect("criar 2a visita enquanto ha visita aberta -> 409", http(
        "POST", f"/chamados/{os_id}/visitas", ADMIN_TOKEN, json={"data_visita": HOJE.isoformat()}), 409)

    est = expect("GET estado da visita (tecnico)", http("GET", base(os_id, vid) + "/estado", tok), 200).json()
    verifica("estado inicial: so 'pode_iniciar_deslocamento_ida'",
             est.get("pode_iniciar_deslocamento_ida") is True and est.get("pode_iniciar_atendimento") is False
             and est.get("pode_pausar_os") is False and est.get("is_os_pausada") is False, str(est))

    # --- ida ---
    expect("iniciar ida (km 1000)", http("POST", base(os_id, vid) + "/iniciar-deslocamento", tok,
           json={"tipo": "ida", "km_inicio": 1000}), 200)
    expect("iniciar ida de novo -> 400", http("POST", base(os_id, vid) + "/iniciar-deslocamento", tok,
           json={"tipo": "ida", "km_inicio": 1000}), 400)
    v = expect("upload-deslocamento (JPEG gerado, inicio da ida)", http(
        "POST", base(os_id, vid) + "/upload-deslocamento", tok, files=arq_jpeg(),
        data={"tipo": "ida", "momento": "inicio"}), 200).json()
    verifica("foto_inicio_ida_url preenchida", bool(v.get("foto_inicio_ida_url")))
    expect("finalizar ida com km menor que o inicio -> 400", http(
        "POST", base(os_id, vid) + "/finalizar-deslocamento", tok, json={"tipo": "ida", "km_fim": 900}), 400)
    expect("finalizar ida (km 1020)", http("POST", base(os_id, vid) + "/finalizar-deslocamento", tok,
           json={"tipo": "ida", "km_fim": 1020}), 200)

    # --- travas do inicio do atendimento: foto de defeito de CADA equipamento (TR-12 / RN-43) ---
    r = expect("iniciar atendimento SEM nenhuma foto de defeito -> 409", http(
        "POST", base(os_id, vid) + "/iniciar-atendimento", tok), 409)
    verifica("409 cita 'foto do defeito' e lista os DOIS equipamentos pendentes",
             "foto do defeito" in r.text and all(s["numero_serie"] in r.text for s in sv), r.resumo())
    expect("foto de CONSERTO antes de iniciar o atendimento -> 409 (PR-42)", http(
        "POST", s0 + "/upload-foto", tok, files=arq_conserto(), data={"tipo": "conserto"}), 409)
    expect("salvar conserto antes de iniciar o atendimento -> 400", http("POST", s0 + "/salvar-conserto", tok, json={}), 400)
    est = http("GET", base(os_id, vid) + "/estado", tok).json()
    verifica("estado: nao pode iniciar, pode registrar foto de defeito e aponta a pendencia",
             est.get("pode_iniciar_atendimento") is False and est.get("pode_registrar_foto_defeito") is True
             and sv[0]["numero_serie"] in (est.get("bloqueio_iniciar_atendimento") or "")
             and [q.get("foto_defeito") for q in est.get("equipamentos") or []] == [False, False], str(est)[:400])
    r = expect("foto de DEFEITO pequena (200x150) do equipamento 1 e aceita (sem resolucao minima)", http(
        "POST", s0 + "/upload-foto", tok, files=arq_jpeg("defeito.jpg", 200, 150), data={"tipo": "defeito"}), 200)
    verifica("upload-foto devolve url, tipo=defeito e id_foto",
             bool(r.json().get("url")) and r.json().get("tipo") == "defeito" and r.json().get("id_foto") is not None)
    r = expect("iniciar atendimento com foto SO do equipamento 1 -> 409", http(
        "POST", base(os_id, vid) + "/iniciar-atendimento", tok), 409)
    verifica("409 lista apenas o equipamento 2", sv[1]["numero_serie"] in r.text and sv[0]["numero_serie"] not in r.text,
             r.resumo())
    verifica("OS continua 'Agendado' (nada foi iniciado)", get_os(os_id).get("status") == "Agendado")
    expect("foto de defeito do equipamento 2", http(
        "POST", base(os_id, vid) + f"/servicos/{sv[1]['id_servico']}/upload-foto", tok, files=arq_jpeg("defeito2.jpg", 120, 90),
        data={"tipo": "defeito"}), 200)
    expect("iniciar atendimento com as duas fotos de defeito", http(
        "POST", base(os_id, vid) + "/iniciar-atendimento", tok), 200)
    verifica("OS passou a 'Em Atendimento'", get_os(os_id).get("status") == "Em Atendimento")

    # --- preencher servicos (PATCH), salvar conserto e foto de conserto por equipamento ---
    s1 = base(os_id, vid) + f"/servicos/{sv[1]['id_servico']}"
    expect("PATCH com defeito fora do enum -> 422", http("PATCH", s0, tok, json={"defeitos_principais": ["Inventado"]}), 422)
    r = expect("salvar conserto do equipamento 1 SEM defeito principal -> 422", http(
        "POST", s0 + "/salvar-conserto", tok, json={}), 422)
    verifica("422 menciona 'defeito principal'", "defeito principal" in r.text, r.resumo())
    expect("finalizar atendimento sem nenhum conserto salvo -> 409", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok,
        json={"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO, "assinatura_base64": assinatura_b64()}), 409)
    r = expect("PATCH do servico do equipamento 1 (defeitos e material de R$ 850)", http("PATCH", s0, tok, json=PATCH_SERVICO_A), 200)
    verifica("servico devolve defeitos e material gravados",
             r.json().get("defeitos_principais") == ["Refrigeração"] and len(r.json().get("materiais_utilizados") or []) == 1, r.resumo())
    verifica("PATCH nao altera modelo/serie (continuam os da OS)", r.json().get("numero_serie") == sv[0]["numero_serie"])
    c1 = expect("salvar conserto do equipamento 1", http("POST", s0 + "/salvar-conserto", tok, json={}), 200).json()
    verifica("conserto_salvo_em preenchido", bool(c1.get("conserto_salvo_em")), str(c1)[:200])
    c1b = http("POST", s0 + "/salvar-conserto", tok, json={}).json()
    verifica("salvar conserto de novo e idempotente (mesma marca de tempo)", c1b.get("conserto_salvo_em") == c1.get("conserto_salvo_em"))
    expect("esvaziar defeitos_principais depois de salvar o conserto -> 422", http(
        "PATCH", s0, tok, json={"defeitos_principais": []}), 422)
    expect("foto de CONSERTO 960x1280 do equipamento 1", http(
        "POST", s0 + "/upload-foto", tok, files=arq_conserto(), data={"tipo": "conserto"}), 200)
    expect("foto de CONSERTO 1280x960 (paisagem) do equipamento 1", http(
        "POST", s0 + "/upload-foto", tok, files={"file": ("conserto2.jpg", jpeg(1280, 960), "image/jpeg")},
        data={"tipo": "conserto"}), 200)
    expect("foto de CONSERTO 800x600 -> 400 (resolucao insuficiente)", http(
        "POST", s0 + "/upload-foto", tok, files={"file": ("pequena.jpg", jpeg(800, 600), "image/jpeg")},
        data={"tipo": "conserto"}), 400)
    expect("upload-foto com tipo invalido -> 400", http("POST", s0 + "/upload-foto", tok, files=arq_jpeg(), data={"tipo": "outro"}), 400)
    fotos = expect("GET fotos do servico 1", http("GET", s0 + "/fotos", tok), 200).json()
    verifica("fotos do equipamento 1: 1 de defeito e 2 de conserto (a de 800x600 nao foi gravada)",
             len(fotos.get("fotos_defeito") or []) == 1 and len(fotos.get("fotos_conserto") or []) == 2, str(fotos)[:300])

    # equipamento 2 ainda pendente: nada de finalizar
    corpo_fim = {"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO, "assinatura_base64": assinatura_b64()}
    r = expect("finalizar atendimento com o equipamento 2 sem conserto -> 409", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok, json=corpo_fim), 409)
    verifica("409 cita a serie do equipamento 2 e nao a do 1", sv[1]["numero_serie"] in r.text and sv[0]["numero_serie"] not in r.text, r.resumo())
    expect("foto de conserto do equipamento 2 ANTES de salvar o conserto e aceita, mas nao basta", http(
        "POST", s1 + "/upload-foto", tok, files=arq_conserto("c2.jpg"), data={"tipo": "conserto"}), 200)
    expect("finalizar de novo (conserto do 2 nao salvo) -> 409", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok, json=corpo_fim), 409)
    expect("PATCH do servico do equipamento 2 (material Filtro 2 x R$ 15)", http("PATCH", s1, tok, json=PATCH_SERVICO_B), 200)
    expect("salvar conserto do equipamento 2", http("POST", s1 + "/salvar-conserto", tok, json={}), 200)
    vis = [x for x in get_os(os_id).get("visitas") or [] if x.get("id_visita") == vid][0]
    verifica("tentativas recusadas nao gravaram assinatura/CPF/nome na visita",
             not vis.get("assinatura_url") and not vis.get("documento_cliente") and not vis.get("nome_cliente_assinatura"), str(vis)[:300])

    # --- finalizar atendimento ---
    expect("finalizar atendimento com CPF invalido -> 422", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok,
        json={**corpo_fim, "documento_cliente": CPF_CLIENTE_INVALIDO}), 422)
    expect("finalizar atendimento com assinatura base64 invalida -> 400", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok,
        json={**corpo_fim, "assinatura_base64": "isto-nao-e-base64!!"}), 400)
    expect("finalizar-dados (descontinuado) -> 410", http("POST", base(os_id, vid) + "/finalizar-dados", tok), 410)
    r = expect("finalizar atendimento com conserto salvo + foto de cada equipamento, CPF valido e assinatura PNG", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok, json=corpo_fim), 200)
    verifica("resposta traz status=ok e assinatura_url", r.json().get("status") == "ok" and bool(r.json().get("assinatura_url")))
    expect("finalizar atendimento de novo -> 400", http("POST", base(os_id, vid) + "/finalizar-atendimento", tok, json=corpo_fim), 400)
    vis = [x for x in http("GET", f"/chamados/{os_id}", tok).json().get("visitas") or [{}] if x.get("id_visita") == vid][0]
    verifica("assinatura, nome e CPF (so digitos) gravados NA VISITA",
             bool(vis.get("assinatura_url")) and vis.get("nome_cliente_assinatura") == "Maria Souza"
             and vis.get("documento_cliente") == "52998224725", f"doc={vis.get('documento_cliente')}")
    verifica("OS ainda 'Em Atendimento' ate a volta", get_os(os_id).get("status") == "Em Atendimento")

    # --- volta ---
    expect("iniciar volta (km 1020)", http("POST", base(os_id, vid) + "/iniciar-deslocamento", tok,
           json={"tipo": "volta", "km_inicio": 1020}), 200)
    expect("upload da foto de inicio da volta", http("POST", base(os_id, vid) + "/upload-deslocamento", tok,
           files=arq_jpeg(), data={"tipo": "volta", "momento": "inicio"}), 200)
    expect("finalizar volta SEM foto de fim -> 400 (odometro obrigatorio se km_total > 0)", http(
        "POST", base(os_id, vid) + "/finalizar-deslocamento", tok, json={"tipo": "volta", "km_fim": 1040}), 400)
    expect("upload da foto de fim da volta", http("POST", base(os_id, vid) + "/upload-deslocamento", tok,
           files=arq_jpeg(), data={"tipo": "volta", "momento": "fim"}), 200)
    r = expect("finalizar volta (km 1040)", http("POST", base(os_id, vid) + "/finalizar-deslocamento", tok,
               json={"tipo": "volta", "km_fim": 1040}), 200)
    verifica("visita finalizada com km_total = 40", r.json().get("servico_finalizado") is True and r.json().get("km_total") == 40,
             f"km_total={r.json().get('km_total')}")

    final = get_os(os_id)
    verifica("OS 'Finalizado' automaticamente, com data_conclusao",
             final.get("status") == "Finalizado" and bool(final.get("data_conclusao")),
             f"status={final.get('status')} data_conclusao={final.get('data_conclusao')}")
    c = expect("GET /custos da OS finalizada", http("GET", f"/chamados/{os_id}/custos", tok), 200).json()
    verifica("custo congelado (congelado=true) com total > 0 e valores_utilizados",
             c.get("congelado") is True and (c.get("total_geral") or 0) > 0 and bool(c.get("valores_utilizados")),
             f"congelado={c.get('congelado')} total={c.get('total_geral')}")
    verifica("custo inclui os materiais dos 2 equipamentos (R$ 850,00 + 2 x R$ 15,00 = R$ 880,00)",
             abs((c.get("custo_total_materiais") or 0) - 880.0) < 0.01, f"materiais={c.get('custo_total_materiais')}")
    c2 = http("GET", f"/chamados/{os_id}/custos", ADMIN_TOKEN).json()
    verifica("admin le o MESMO snapshot (total identico)", c2.get("total_geral") == c.get("total_geral") and c2.get("congelado") is True)

    # fechamentos de porta
    r = http("POST", f"/chamados/{os_id}/concluir", ADMIN_TOKEN)
    expect("POST /concluir nao existe mais -> 404/405", r, (404, 405))
    expect("tecnico PATCH status -> 403", http("PATCH", f"/chamados/{os_id}", tok, json={"status": "Finalizado"}), 403)
    expect("admin PATCH status=Finalizado -> 403", http("PATCH", f"/chamados/{os_id}", ADMIN_TOKEN,
           json={"status": "Finalizado"}), 403)
    expect("admin PATCH is_cancelled -> 400 (use /cancelar)", http("PATCH", f"/chamados/{os_id}", ADMIN_TOKEN,
           json={"is_cancelled": True}), 400)
    expect("alterar visita de OS finalizada -> 409", http("PATCH", base(os_id, vid), ADMIN_TOKEN,
           json={"descricao_servico_executado": "tentativa"}), 409)

    Ctx.os_final, Ctx.os_final_vid = os_id, vid
    Ctx.os_final_servicos = [s["id_servico"] for s in sv]
    Ctx.os_final_materiais = c.get("custo_total_materiais")


# =====================================================================================================================
# d) Cenario 2 - pausa e reagendamento (a visita nova exige fotos de novo)
# =====================================================================================================================

def cenario_2_pausa_reagendamento() -> None:
    if Ctx.cliente_id is None or Ctx.tec1 is None or not Ctx.tec1.token:
        P.pulou("cenario 2", "cliente/tecnico de teste nao foram criados")
        return
    tec, tok = Ctx.tec1, Ctx.tec1.token
    os_ = nova_os(Ctx.cliente_id, None, "cenario2")
    if os_ is None:
        return
    os_id = os_["id_os"]
    if not pre("atribuir tecnico", http("PATCH", f"/chamados/{os_id}", ADMIN_TOKEN, json={"id_tecnico_atribuido": tec.id})):
        return
    vid = fluxo_ate_atendimento(os_id, tok)
    if vid is None:
        return
    verifica("ida completa, foto de defeito e atendimento iniciado: OS 'Em Atendimento'", get_os(os_id).get("status") == "Em Atendimento")
    pb = base(os_id, vid) + "/pausar"

    expect("admin pausa com motivo 'Outro' SEM descricao -> 422", http("POST", pb, ADMIN_TOKEN, json={"motivo": "Outro"}), 422)
    expect("admin pausa com motivo 'Outro' e descricao so de espacos -> 422",
           http("POST", pb, ADMIN_TOKEN, json={"motivo": "Outro", "descricao": "   "}), 422)
    expect("pausa com motivo livre 'Almoço' -> 422", http("POST", pb, ADMIN_TOKEN, json={"motivo": "Almoço"}), 422)
    r = expect("admin pausa com 'Outro' + descricao (conserto ainda pendente: pausa dispensa as travas)", http(
        "POST", pb, ADMIN_TOKEN, json={"motivo": "Outro", "descricao": "Cliente pediu para aguardar o gerente"}), 200)
    d = r.json()
    verifica("pausa registra por_papel=admin, por_usuario_id do admin e is_ativa=true",
             d.get("por_papel") == "admin" and d.get("por_usuario_id") == ADMIN_ID and d.get("is_ativa") is True, str(d))
    verifica("OS passou a 'Pausado'", get_os(os_id).get("status") == "Pausado")
    expect("pausar de novo -> 400/409", http("POST", pb, ADMIN_TOKEN, json={"motivo": "Peça pendente"}), (400, 409))

    est = http("GET", base(os_id, vid) + "/estado", tok).json()
    verifica("estado: is_os_pausada, motivo 'Outro', nao pode finalizar atendimento, pode iniciar volta",
             est.get("is_os_pausada") is True and est.get("motivo_pausa") == "Outro"
             and est.get("pode_finalizar_atendimento") is False and est.get("pode_iniciar_deslocamento_volta") is True, str(est))

    future = (HOJE + timedelta(days=3)).isoformat()
    expect("admin tenta reagendar OS Pausado -> 409", http("POST", f"/chamados/{os_id}/reagendar", ADMIN_TOKEN,
           json={"data_visita": future}), 409)
    expect("tecnico tenta finalizar atendimento com OS pausada -> 400 (a checagem de pausa vem antes das travas)", http(
        "POST", base(os_id, vid) + "/finalizar-atendimento", tok,
        json={"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO,
              "assinatura_base64": assinatura_b64()}), 400)
    sv_old = servicos_da_visita(os_id, vid, tok)
    if sv_old:
        expect("salvar conserto com a OS pausada -> 400", http(
            "POST", base(os_id, vid) + f"/servicos/{sv_old[0]['id_servico']}/salvar-conserto", tok, json={}), 400)

    r = volta_completa(os_id, vid, tok, quiet=False)
    if r.status_code != 200:
        return
    os_apos = get_os(os_id)
    verifica("volta com pausa ativa -> OS 'Aguardando Reagendamento' (e NAO Finalizado)",
             os_apos.get("status") == "Aguardando Reagendamento" and not os_apos.get("data_conclusao"),
             f"status={os_apos.get('status')}")
    v_old = [x for x in os_apos.get("visitas", []) if x["id_visita"] == vid][0]
    verifica("pausa continua ativa ate o reagendamento", any(p["is_ativa"] for p in v_old.get("pausas", [])))
    c = custos(os_id)
    verifica("custo NAO congelado enquanto a OS nao finaliza", c.get("congelado") is False, f"congelado={c.get('congelado')}")

    passada = (HOJE - timedelta(days=1)).isoformat()
    expect("reagendar com data passada -> 422", http("POST", f"/chamados/{os_id}/reagendar", ADMIN_TOKEN,
           json={"data_visita": passada}), 422)
    expect("tecnico tenta reagendar -> 403", http("POST", f"/chamados/{os_id}/reagendar", tok,
           json={"data_visita": future}), 403)
    r = expect("admin reagenda com data futura -> nova visita", http(
        "POST", f"/chamados/{os_id}/reagendar", ADMIN_TOKEN, json={"data_visita": future}), (200, 201))
    verifica("reagendar de 'Aguardando Reagendamento' devolve 201 e a nova visita", r.status_code == 201
             and r.json().get("data_visita") == future and r.json().get("id_visita") != vid, r.resumo())
    os_novo = get_os(os_id)
    visitas = os_novo.get("visitas", [])
    verifica("OS voltou a 'Agendado' com data_agendamento = nova data e 2 visitas",
             os_novo.get("status") == "Agendado" and os_novo.get("data_agendamento") == future and len(visitas) == 2,
             f"status={os_novo.get('status')} ag={os_novo.get('data_agendamento')} visitas={len(visitas)}")
    antiga = [x for x in visitas if x["id_visita"] == vid]
    verifica("pausa da visita antiga ENCERRADA (is_ativa=false, encerrada_em preenchida) e historico preservado",
             bool(antiga) and antiga[0]["pausas"] and all((not p["is_ativa"]) and p["encerrada_em"] for p in antiga[0]["pausas"])
             and antiga[0]["servico_finalizado"] is True and bool(antiga[0].get("ida_inicio_em")), str(antiga[:1]))
    nova_vid = max(x["id_visita"] for x in visitas)
    est = http("GET", base(os_id, nova_vid) + "/estado", tok).json()
    verifica("tecnico ve a nova visita pronta para iniciar a ida", est.get("pode_iniciar_deslocamento_ida") is True, str(est))
    est_old = http("GET", base(os_id, vid) + "/estado", tok).json()
    verifica("visita antiga (historico) nao oferece nenhuma acao nem pendencia", est_old.get("pode_iniciar_deslocamento_ida") is False
             and est_old.get("pode_iniciar_atendimento") is False and est_old.get("pode_pausar_os") is False
             and est_old.get("visita_vigente") is False and est_old.get("equipamentos") == [], str(est_old))

    # a visita nova nasce com 1 servico por equipamento, SEM fotos (as da visita 1 nao valem)
    sv_new = servicos_da_visita(os_id, nova_vid, tok)
    verifica("visita nova tem 1 registro de servico por equipamento, sem fotos de defeito",
             len(sv_new) == 1 and sv_new[0].get("fotos_defeito") == [] and sv_new[0].get("conserto_salvo_em") is None, str(sv_new)[:300])

    # Reagendar Agendado com ida nao iniciada: altera a data da visita existente (200)
    outra = (HOJE + timedelta(days=5)).isoformat()
    r = expect("reagendar 'Agendado' sem ida iniciada altera a data da visita existente -> 200", http(
        "POST", f"/chamados/{os_id}/reagendar", ADMIN_TOKEN, json={"data_visita": outra}), 200)
    verifica("mesma visita, nova data, ainda 2 visitas", r.json().get("id_visita") == nova_vid
             and len(get_os(os_id).get("visitas", [])) == 2, r.resumo())

    # cada visita exige de novo a foto de defeito (T-52)
    if ida_completa(os_id, nova_vid, tok, km0=2000, quiet=False):
        expect("visita nova: iniciar atendimento SEM foto de defeito -> 409 (fotos da visita 1 nao valem)", http(
            "POST", base(os_id, nova_vid) + "/iniciar-atendimento", tok), 409)
        verifica("visita nova: depois das fotos de defeito, o atendimento inicia",
                 iniciar_atendimento(os_id, nova_vid, tok, quiet=True) and get_os(os_id).get("status") == "Em Atendimento")


# =====================================================================================================================
# e) Cenario 3 - cancelamento
# =====================================================================================================================

def cenario_3_cancelamento() -> None:
    if Ctx.cliente_id is None:
        P.pulou("cenario 3", "cliente de teste nao foi criado")
        return
    os_ = nova_os(Ctx.cliente_id, None, "cenario3")
    if os_ is None:
        return
    os_id = os_["id_os"]
    cb = f"/chamados/{os_id}/cancelar"
    expect("cancelar sem corpo/motivo -> 422", http("POST", cb, ADMIN_TOKEN, json={}), 422)
    expect("cancelar com motivo vazio (espacos) -> 422", http("POST", cb, ADMIN_TOKEN, json={"motivo": "   "}), 422)
    expect("cancelar com motivo > 500 caracteres -> 422", http("POST", cb, ADMIN_TOKEN, json={"motivo": "x" * 501}), 422)
    if Ctx.tec1 and Ctx.tec1.token:
        expect("tecnico tenta cancelar -> 403", http("POST", cb, Ctx.tec1.token, json={"motivo": "teste"}), 403)
    r = expect("cancelar com motivo", http("POST", cb, ADMIN_TOKEN, json={"motivo": "Cliente desmarcou (smoke)"}), 200)
    d = r.json()
    verifica("OS cancelada: is_cancelled, motivo, cancelado_em e cancelado_por=admin",
             d.get("is_cancelled") is True and d.get("motivo_cancelamento") == "Cliente desmarcou (smoke)"
             and bool(d.get("cancelado_em")) and d.get("cancelado_por") == ADMIN_ID, str(d)[:300])
    expect("cancelar de novo -> 409", http("POST", cb, ADMIN_TOKEN, json={"motivo": "outra vez"}), 409)
    expect("GET da OS cancelada -> 404", http("GET", f"/chamados/{os_id}", ADMIN_TOKEN), 404)
    lista = http("GET", "/chamados/?is_cancelled=true", ADMIN_TOKEN).json()
    verifica("admin ainda encontra a OS em /chamados/?is_cancelled=true",
             isinstance(lista, list) and os_id in [o["id_os"] for o in lista])
    expect("reagendar OS cancelada -> 404", http("POST", f"/chamados/{os_id}/reagendar", ADMIN_TOKEN,
           json={"data_visita": (HOJE + timedelta(days=2)).isoformat()}), 404)
    eq0 = (os_.get("equipamentos") or [{}])[0].get("id_os_equipamento")
    expect("vincular equipamento a OS cancelada -> 409", http(
        "POST", f"/chamados/{os_id}/equipamentos", ADMIN_TOKEN,
        json={"id_equipamento_modelo": Ctx.modelo_id, "numero_serie": f"CANC-{RUN_ID}"}), 409)
    if eq0:
        expect("remover equipamento de OS cancelada -> 409", http("DELETE", f"/chamados/{os_id}/equipamentos/{eq0}", ADMIN_TOKEN), 409)

    _cancelar_com_pausa_ativa()

    if Ctx.os_final is None:
        P.pulou("cancelar OS Finalizada -> 409", "cenario 1 nao finalizou uma OS")
    else:
        expect("cancelar OS Finalizada -> 409", http("POST", f"/chamados/{Ctx.os_final}/cancelar", ADMIN_TOKEN,
               json={"motivo": "nao deve cancelar"}), 409)
        verifica("OS Finalizada segue intacta (nao cancelada)", get_os(Ctx.os_final).get("is_cancelled") is False)


def _cancelar_com_pausa_ativa() -> None:
    """6.9: cancelar OS pausada encerra a pausa ativa e mantem visitas/servicos; tecnico deixa de ve-la."""
    if Ctx.tec1 is None or not Ctx.tec1.token:
        P.pulou("cancelar OS pausada", "tecnico de teste ausente")
        return
    tec, tok = Ctx.tec1, Ctx.tec1.token
    os_ = nova_os(Ctx.cliente_id, tec.id, "cenario3-pausada")
    if os_ is None:
        return
    os_id = os_["id_os"]
    vid = fluxo_ate_atendimento(os_id, tok)
    if vid is None:
        return
    sv = servicos_da_visita(os_id, vid, tok)
    if sv:
        pre("preencher servico (preparacao)", http("PATCH", base(os_id, vid) + f"/servicos/{sv[0]['id_servico']}", tok,
                                                   json=PATCH_SERVICO_A))
    pre("pausar (preparacao)", http("POST", base(os_id, vid) + "/pausar", ADMIN_TOKEN, json={"motivo": "Peça pendente"}))
    verifica("preparacao: OS 'Pausado'", get_os(os_id).get("status") == "Pausado")
    expect("cancelar OS Pausado com motivo", http("POST", f"/chamados/{os_id}/cancelar", ADMIN_TOKEN,
           json={"motivo": "Cancelada durante a pausa (smoke)"}), 200)
    lista = http("GET", "/chamados/?is_cancelled=true", ADMIN_TOKEN).json()
    achada = [o for o in lista if o["id_os"] == os_id] if isinstance(lista, list) else []
    visitas = achada[0]["visitas"] if achada else []
    verifica("pausas ativas encerradas ao cancelar e visita/servico preservados",
             bool(visitas) and all(not p["is_ativa"] and p["encerrada_em"] for v in visitas for p in v["pausas"])
             and any(v["servicos_realizados"] for v in visitas), str(visitas)[:300])
    expect("tecnico GET da OS cancelada -> 404", http("GET", f"/chamados/{os_id}", tok), 404)
    lt = http("GET", "/chamados/", tok).json()
    verifica("tecnico nao ve a OS cancelada na propria lista", isinstance(lt, list) and os_id not in [o["id_os"] for o in lt])


# =====================================================================================================================
# f) Cenario 4 - permissoes
# =====================================================================================================================

def cenario_4_permissoes() -> None:
    if Ctx.cliente_id is None or Ctx.tec1 is None or not Ctx.tec1.token:
        P.pulou("cenario 4", "cliente/tecnico de teste nao foram criados")
        return
    tec1, t1 = Ctx.tec1, Ctx.tec1.token
    tec2 = novo_tecnico("tec2", quiet=False)
    cliente_alheio = novo_cliente("-alheio")
    os_ = nova_os(Ctx.cliente_id, tec1.id, "cenario4")
    if tec2 is None or os_ is None or cliente_alheio is None:
        return
    t2, os_id = tec2.token, os_["id_os"]
    vid = (os_.get("visitas") or [{}])[0].get("id_visita")
    verifica("criar OS ja com tecnico -> 'Agendado' + 1 visita", os_["status"] == "Agendado" and vid is not None)
    if vid is None:
        return
    sv = servicos_da_visita(os_id, vid, t1)

    expect("tecnico 2 GET na OS do tecnico 1 -> 403", http("GET", f"/chamados/{os_id}", t2), 403)
    expect("tecnico 2 GET estado da visita do tecnico 1 -> 403", http("GET", base(os_id, vid) + "/estado", t2), 403)
    expect("tecnico 2 GET equipamentos da OS do tecnico 1 -> 403", http("GET", f"/chamados/{os_id}/equipamentos", t2), 403)
    expect("tecnico 2 GET servicos da visita do tecnico 1 -> 403", http("GET", base(os_id, vid) + "/servicos", t2), 403)
    if sv:
        sb = base(os_id, vid) + f"/servicos/{sv[0]['id_servico']}"
        expect("tecnico 2 PATCH servico do tecnico 1 -> 403", http("PATCH", sb, t2, json={"defeitos_principais": ["Refrigeração"]}), 403)
        expect("tecnico 2 salvar-conserto na OS do tecnico 1 -> 403", http("POST", sb + "/salvar-conserto", t2, json={}), 403)
        expect("tecnico 2 upload-foto na OS do tecnico 1 -> 403", http(
            "POST", sb + "/upload-foto", t2, files=arq_jpeg(), data={"tipo": "defeito"}), 403)
    expect("tecnico 2 iniciar deslocamento na OS do tecnico 1 -> 403", http(
        "POST", base(os_id, vid) + "/iniciar-deslocamento", t2, json={"tipo": "ida", "km_inicio": 5}), 403)
    expect("tecnico 2 upload-deslocamento na OS do tecnico 1 -> 403", http(
        "POST", base(os_id, vid) + "/upload-deslocamento", t2, files=arq_jpeg(), data={"tipo": "ida", "momento": "inicio"}), 403)
    expect("tecnico 2 GET custos da OS do tecnico 1 -> 403", http("GET", f"/chamados/{os_id}/custos", t2), 403)
    lista2 = http("GET", "/chamados/", t2).json()
    verifica("lista do tecnico 2 NAO contem a OS do tecnico 1",
             isinstance(lista2, list) and os_id not in [o["id_os"] for o in lista2])

    # servico/equipamento de OUTRA visita/OS na URL -> 404 (nao vaza nem altera)
    outra = nova_os(Ctx.cliente_id, tec1.id, "cenario4-outra")
    if outra is not None and sv:
        ovid = (outra.get("visitas") or [{}])[0].get("id_visita")
        if ovid is not None:
            expect("servico de OUTRA visita na URL (PATCH) -> 404", http(
                "PATCH", base(outra["id_os"], ovid) + f"/servicos/{sv[0]['id_servico']}", t1,
                json={"defeitos_principais": ["Refrigeração"]}), 404)
            eq_outra = (outra.get("equipamentos") or [{}])[0].get("id_os_equipamento")
            expect("equipamento de OUTRA OS na URL (PATCH do admin) -> 404/409", http(
                "PATCH", f"/chamados/{os_id}/equipamentos/{eq_outra}", ADMIN_TOKEN, json={"numero_serie": "Z"}), (404, 409))

    expect("tecnico chama POST /chamados -> 403", http("POST", "/chamados/", t1, json={
        "id_cliente": Ctx.cliente_id, "descricao_cliente": f"{PREFIXO}nao deve criar", "equipamentos": equipamentos(1)}), 403)
    expect("tecnico chama GET /tecnicos -> 403", http("GET", "/tecnicos/", t1), 403)
    expect("tecnico chama GET /tecnicos/{id} -> 403", http("GET", f"/tecnicos/{tec2.id}", t1), 403)
    expect("tecnico chama GET /clientes (lista) -> 403", http("GET", "/clientes/", t1), 403)
    expect("tecnico chama POST /clientes -> 403", http("POST", "/clientes/", t1, json={}), 403)
    expect("tecnico PATCH em OS -> 403", http("PATCH", f"/chamados/{os_id}", t1, json={"descricao_cliente": "x"}), 403)
    expect("tecnico POST /cancelar -> 403", http("POST", f"/chamados/{os_id}/cancelar", t1, json={"motivo": "x"}), 403)
    expect("tecnico DELETE /tecnicos/{id} -> 403", http("DELETE", f"/tecnicos/{tec2.id}", t1), 403)
    expect("tecnico GET /clientes/{id} de cliente que NAO e dele -> 403", http("GET", f"/clientes/{cliente_alheio}", t1), 403)
    expect("tecnico GET /clientes/{id} inexistente -> 403 (nao revela ids)", http("GET", "/clientes/2147000000", t1), 403)
    expect("tecnico GET /clientes/{id} do cliente da PROPRIA OS -> 200", http("GET", f"/clientes/{Ctx.cliente_id}", t1), 200)
    expect("admin PATCH id_tecnico_atribuido=tecnico inexistente -> 404", http(
        "PATCH", f"/chamados/{os_id}", ADMIN_TOKEN, json={"id_tecnico_atribuido": 2147000000}), 404)
    expect("admin tenta iniciar deslocamento (rota so de tecnico) -> 403", http(
        "POST", base(os_id, vid) + "/iniciar-deslocamento", ADMIN_TOKEN, json={"tipo": "ida", "km_inicio": 5}), 403)
    expect("sem token em GET /chamados -> 401", http("GET", "/chamados/"), 401)
    expect("sem token em POST /chamados -> 401", http("POST", "/chamados/", json={}), 401)
    expect("sem token em GET /equipamentos -> 401", http("GET", "/equipamentos/"), 401)


# =====================================================================================================================
# g) Cenario 5 - desativacao do tecnico (RN-08a)
# =====================================================================================================================

def cenario_5_desativacao() -> None:
    if Ctx.cliente_id is None:
        P.pulou("cenario 5", "cliente de teste nao foi criado")
        return
    tec3, tec4 = novo_tecnico("tec3", quiet=False), novo_tecnico("tec4")
    if tec3 is None or tec4 is None:
        return
    t3 = tec3.token
    os_ag = nova_os(Ctx.cliente_id, tec3.id, "cen5-agendada")
    os_at = nova_os(Ctx.cliente_id, tec3.id, "cen5-em-atendimento")
    os_fi = nova_os(Ctx.cliente_id, tec3.id, "cen5-finalizada")
    if not (os_ag and os_at and os_fi):
        return
    id_ag, id_at, id_fi = os_ag["id_os"], os_at["id_os"], os_fi["id_os"]

    vid_at = fluxo_ate_atendimento(id_at, t3)
    ok_fin = fluxo_completo(id_fi, t3)
    verifica("preparacao: 1 OS Agendada, 1 Em Atendimento, 1 Finalizada do mesmo tecnico",
             get_os(id_ag).get("status") == "Agendado" and get_os(id_at).get("status") == "Em Atendimento"
             and ok_fin and get_os(id_fi).get("status") == "Finalizado")
    if vid_at is None or not ok_fin:
        return
    vis_at_antes = [v for v in get_os(id_at)["visitas"] if v["id_visita"] == vid_at][0]
    fin_antes = get_os(id_fi)
    custo_antes = custos(id_fi).get("total_geral")
    vid_ag = (get_os(id_ag).get("visitas") or [{}])[0].get("id_visita")

    expect("admin desativa o tecnico (DELETE) -> 204", http("DELETE", f"/tecnicos/{tec3.id}", ADMIN_TOKEN), 204)
    ag, at, fi = get_os(id_ag), get_os(id_at), get_os(id_fi)
    verifica("OS Agendada -> 'Pendente' sem tecnico", ag.get("status") == "Pendente" and ag.get("id_tecnico_atribuido") is None,
             f"status={ag.get('status')} tec={ag.get('id_tecnico_atribuido')}")
    verifica("OS Em Atendimento -> 'Pendente' sem tecnico", at.get("status") == "Pendente" and at.get("id_tecnico_atribuido") is None,
             f"status={at.get('status')} tec={at.get('id_tecnico_atribuido')}")
    verifica("OS Finalizada permanece intacta (status, tecnico, data_conclusao)",
             fi.get("status") == "Finalizado" and fi.get("id_tecnico_atribuido") == tec3.id
             and fi.get("data_conclusao") == fin_antes.get("data_conclusao"))
    verifica("custo congelado da OS finalizada inalterado", custos(id_fi).get("total_geral") == custo_antes)
    verifica("equipamentos das OS desatribuidas continuam vinculados (historico)",
             len(ag.get("equipamentos") or []) == 1 and len(at.get("equipamentos") or []) == 1)
    vis_at_dep = [v for v in at["visitas"] if v["id_visita"] == vid_at]
    verifica("historico da visita iniciada preservado (ida_inicio_em e atendimento_inicio_em)",
             bool(vis_at_dep) and vis_at_dep[0].get("ida_inicio_em") == vis_at_antes.get("ida_inicio_em")
             and bool(vis_at_dep[0].get("atendimento_inicio_em")))
    verifica("visita e fotos da OS Em Atendimento nao foram apagadas", len(at["visitas"]) >= 1
             and any(s.get("fotos_defeito") for s in servicos_da_visita(id_at, vid_at)))

    expect("token ANTIGO do tecnico desativado -> 401 em /auth/me", http("GET", "/auth/me", t3), 401)
    expect("token antigo do tecnico desativado -> 401 em /chamados", http("GET", "/chamados/", t3), 401)
    expect("token antigo do tecnico desativado -> 401 em /sync/minhas-os", http("GET", "/sync/minhas-os", t3), 401)
    expect("login do tecnico desativado -> 401", login(tec3.email, SENHA_TECNICO), 401)
    expect("desativar de novo e idempotente -> 204", http("DELETE", f"/tecnicos/{tec3.id}", ADMIN_TOKEN), 204)

    if ADMIN_ID is not None:
        expect("admin tenta atribuir ADMIN a uma OS -> 400", http(
            "PATCH", f"/chamados/{id_ag}", ADMIN_TOKEN, json={"id_tecnico_atribuido": ADMIN_ID}), 400)
    expect("atribuir tecnico DESATIVADO -> 404", http(
        "PATCH", f"/chamados/{id_ag}", ADMIN_TOKEN, json={"id_tecnico_atribuido": tec3.id}), 404)
    expect("reagendar OS Pendente -> 409", http("POST", f"/chamados/{id_ag}/reagendar", ADMIN_TOKEN,
           json={"data_visita": (HOJE + timedelta(days=2)).isoformat()}), 409)

    # reatribuicao da OS que estava Em Atendimento: visita nova (que exige as fotos de novo)
    r = expect("reatribuir a OS (ex-Em Atendimento) ao novo tecnico", http(
        "PATCH", f"/chamados/{id_at}", ADMIN_TOKEN, json={"id_tecnico_atribuido": tec4.id}), 200)
    d = r.json()
    visitas = d.get("visitas") or []
    verifica("OS 'Agendado' com tecnico novo e visita NOVA criada (a antiga fica como historico)",
             d.get("status") == "Agendado" and d.get("id_tecnico_atribuido") == tec4.id and len(visitas) == 2,
             f"status={d.get('status')} visitas={len(visitas)}")
    if len(visitas) == 2:
        nova = max(v["id_visita"] for v in visitas)
        verifica("visita nova nao herda marcos da antiga", [v for v in visitas if v["id_visita"] == nova][0].get("ida_inicio_em") is None)
        est = expect("novo tecnico GET estado da visita nova", http("GET", base(id_at, nova) + "/estado", tec4.token), 200).json()
        verifica("estado da visita nova: pode iniciar a ida", est.get("pode_iniciar_deslocamento_ida") is True, str(est))
        sv_new = servicos_da_visita(id_at, nova, tec4.token)
        verifica("visita nova tem 1 servico por equipamento, sem fotos (nao herda as do tecnico anterior)",
                 len(sv_new) == 1 and sv_new[0].get("fotos_defeito") == [], str(sv_new)[:200])
        expect("novo tecnico NAO executa a visita antiga abandonada -> 409", http(
            "POST", base(id_at, vid_at) + "/iniciar-deslocamento", tec4.token, json={"tipo": "ida", "km_inicio": 10}), 409)
        ok = ida_completa(id_at, nova, tec4.token, km0=2000, quiet=False)
        verifica("fluxo da visita nova comeca normalmente (ida completa)", ok)

    # reatribuicao da OS que estava so Agendada: visita reaproveitada (nenhuma ida iniciada)
    r = expect("reatribuir a OS (ex-Agendada) ao novo tecnico", http(
        "PATCH", f"/chamados/{id_ag}", ADMIN_TOKEN, json={"id_tecnico_atribuido": tec4.id}), 200)
    d = r.json()
    verifica("OS ex-Agendada volta a 'Agendado' e mantem UMA visita aberta (reaproveitada)",
             d.get("status") == "Agendado" and len(d.get("visitas") or []) == 1
             and (d["visitas"][0]["id_visita"] == vid_ag if d.get("visitas") else False),
             f"status={d.get('status')} visitas={len(d.get('visitas') or [])}")


# =====================================================================================================================
# h) Cenario 6 - uploads
# =====================================================================================================================

def cenario_6_uploads() -> None:
    if Ctx.cliente_id is None:
        P.pulou("cenario 6", "cliente de teste nao foi criado")
        return
    tec = novo_tecnico("tec-upload")
    if tec is None:
        return
    tok = tec.token
    os_ = nova_os(Ctx.cliente_id, tec.id, "cenario6")
    if os_ is None:
        return
    os_id = os_["id_os"]
    vid = (os_.get("visitas") or [{}])[0].get("id_visita")
    if vid is None:
        P.falhou("OS do cenario 6 sem visita automatica")
        return
    if not pre("iniciar ida (preparacao)", http("POST", base(os_id, vid) + "/iniciar-deslocamento", tok,
                                                json={"tipo": "ida", "km_inicio": 10})):
        return
    up = base(os_id, vid) + "/upload-deslocamento"
    form = {"tipo": "ida", "momento": "inicio"}

    expect("arquivo de texto com nome .jpg e Content-Type image/jpeg -> 422",
           http("POST", up, tok, files={"file": ("falso.jpg", b"isto nao e uma imagem", "image/jpeg")}, data=form), 422)
    expect("arquivo vazio -> 422", http("POST", up, tok, files={"file": ("vazio.jpg", b"", "image/jpeg")}, data=form), 422)
    expect("GIF (imagem valida, mas formato nao permitido) -> 422",
           http("POST", up, tok, files={"file": ("a.gif", gif(), "image/gif")}, data=form), 422)
    expect("PDF disfarcado de imagem -> 422",
           http("POST", up, tok, files={"file": ("a.png", b"%PDF-1.4\n%fake\n", "image/png")}, data=form), 422)
    expect("PNG valido e aceito", http("POST", up, tok, files={"file": ("a.png", png(120, 90), "image/png")}, data=form), 200)
    expect("upload-deslocamento com 'tipo' invalido -> 400", http(
        "POST", up, tok, files=arq_jpeg(), data={"tipo": "meio", "momento": "inicio"}), 400)
    expect("upload-deslocamento com 'momento' invalido -> 400", http(
        "POST", up, tok, files=arq_jpeg(), data={"tipo": "ida", "momento": "meio"}), 400)
    expect("upload_file com file_type invalido -> 400", http(
        "POST", base(os_id, vid) + "/upload_file", tok, files=arq_jpeg(), data={"file_type": "campo_inexistente"}), 400)
    expect("upload_file de comprovante de pedagio (JPEG) -> 200", http(
        "POST", base(os_id, vid) + "/upload_file", tok, files=arq_jpeg(), data={"file_type": "comprovante_pedagio_urls"}), 200)

    sv = servicos_da_visita(os_id, vid, tok)
    if sv:
        sb = base(os_id, vid) + f"/servicos/{sv[0]['id_servico']}"
        expect("foto de defeito de servico: arquivo de texto disfarcado de JPEG -> 422", http(
            "POST", sb + "/upload-foto", tok, files={"file": ("falso.jpg", b"nao e imagem", "image/jpeg")},
            data={"tipo": "defeito"}), 422)
        expect("foto de defeito de servico: PNG valido -> 200", http(
            "POST", sb + "/upload-foto", tok, files={"file": ("d.png", png(80, 60), "image/png")}, data={"tipo": "defeito"}), 200)

    if SKIP_BIG:
        P.pulou("imagem > 15 MB -> 413", "SMOKE_SKIP_BIG_UPLOAD=1")
    else:
        grande = b"\xff\xd8\xff\xe0" + b"\x00" * (15 * 1024 * 1024 + 4096)  # cabecalho JPEG + preenchimento > 15 MB
        r = http("POST", up, tok, files={"file": ("grande.jpg", grande, "image/jpeg")}, data=form)
        expect("imagem > 15 MB -> 413", r, 413)
        del grande
        expect("API continua saudavel apos o upload grande (/auth/me)", http("GET", "/auth/me", tok), 200)

    # Escritas do TECNICO em OS Finalizada -> 409 (reaproveita a OS do cenario 1)
    if Ctx.os_final is None or Ctx.tec1 is None or not Ctx.tec1.token or Ctx.os_final_vid is None:
        P.pulou("escritas em OS Finalizada -> 409", "cenario 1 nao finalizou uma OS")
        return
    t1, of, ov = Ctx.tec1.token, Ctx.os_final, Ctx.os_final_vid
    expect("upload-deslocamento em OS Finalizada -> 409", http(
        "POST", base(of, ov) + "/upload-deslocamento", t1, files=arq_jpeg(), data=form), 409)
    expect("upload_file em OS Finalizada -> 409", http(
        "POST", base(of, ov) + "/upload_file", t1, files=arq_jpeg(), data={"file_type": "odometro_inicio_url"}), 409)
    if Ctx.os_final_servicos:
        sid = Ctx.os_final_servicos[0]
        expect("tecnico: upload-foto de servico em OS Finalizada -> 409", http(
            "POST", base(of, ov) + f"/servicos/{sid}/upload-foto", t1, files=arq_jpeg(), data={"tipo": "defeito"}), 409)
        expect("tecnico: PATCH de servico em OS Finalizada -> 409 (so o admin corrige fotos/materiais)", http(
            "PATCH", base(of, ov) + f"/servicos/{sid}", t1, json={"materiais_utilizados": []}), 409)
        expect("tecnico: salvar-conserto em OS Finalizada -> 409/400", http(
            "POST", base(of, ov) + f"/servicos/{sid}/salvar-conserto", t1, json={}), (400, 409))
        expect("tecnico: POST .../servicos (descontinuado) -> 410", http("POST", base(of, ov) + "/servicos", t1, json={}), 410)
        c = custos(of, t1)
        verifica("snapshot de custo da OS Finalizada intacto (materiais congelados)", c.get("congelado") is True
                 and Ctx.os_final_materiais is not None and abs((c.get("custo_total_materiais") or 0) - Ctx.os_final_materiais) < 0.01,
                 f"materiais={c.get('custo_total_materiais')} esperado={Ctx.os_final_materiais}")


# =====================================================================================================================
# i) Cenario 7 - equipamentos da OS: edicao do admin ate o inicio do atendimento
# =====================================================================================================================

def cenario_7_equipamentos_admin() -> None:
    if Ctx.cliente_id is None or Ctx.tec1 is None or not Ctx.tec1.token or Ctx.modelo_id is None or Ctx.modelo2_id is None:
        P.pulou("cenario 7", "cliente/tecnico/modelos de teste nao foram criados")
        return
    tec, tok = Ctx.tec1, Ctx.tec1.token
    mid, mid2 = Ctx.modelo_id, Ctx.modelo2_id
    os_ = nova_os(Ctx.cliente_id, tec.id, "cenario7", n_equip=2)
    if os_ is None:
        return
    os_id = os_["id_os"]
    vid = (os_.get("visitas") or [{}])[0].get("id_visita")
    eqs = os_.get("equipamentos") or []
    if vid is None or len(eqs) != 2:
        P.falhou("OS do cenario 7 sem visita automatica/2 equipamentos")
        return
    e1, e2 = eqs
    eb = f"/chamados/{os_id}/equipamentos"
    serie1, serie2 = e1["numero_serie"], e2["numero_serie"]

    # corrige serie e modelo antes de iniciar (auditado)
    r = expect("admin corrige serie e modelo do equipamento 1 antes de iniciar -> 200", http(
        "PATCH", f"{eb}/{e1['id_os_equipamento']}", ADMIN_TOKEN, json={"numero_serie": serie1 + "-B", "id_equipamento_modelo": mid2}), 200)
    verifica("resposta traz a nova serie e o novo modelo", r.json().get("numero_serie") == serie1 + "-B"
             and r.json().get("id_equipamento_modelo") == mid2, r.resumo())
    sv = servicos_da_visita(os_id, vid, tok)
    verifica("o registro de servico exibe a serie corrigida", serie1 + "-B" in [s.get("numero_serie") for s in sv], str(sv)[:300])
    expect("corrigir serie para uma que ja existe na OS (ignora maiusculas) -> 409", http(
        "PATCH", f"{eb}/{e1['id_os_equipamento']}", ADMIN_TOKEN, json={"numero_serie": serie2.lower()}), 409)
    expect("PATCH de equipamento sem corpo -> 400/422", http("PATCH", f"{eb}/{e1['id_os_equipamento']}", ADMIN_TOKEN, json={}), (400, 422))
    expect("vincular equipamento com serie ja existente na OS (ignora maiusculas) -> 409", http(
        "POST", eb, ADMIN_TOKEN, json={"id_equipamento_modelo": mid, "numero_serie": f"  {serie2.lower()} "}), 409)
    expect("vincular equipamento com modelo inexistente -> 404/422", http(
        "POST", eb, ADMIN_TOKEN, json={"id_equipamento_modelo": 2147000000, "numero_serie": f"X-{RUN_ID}"}), (404, 422))

    # vincular um terceiro equipamento com a visita aberta cria o registro de servico dele
    r = expect("admin vincula um 3o equipamento -> 201", http(
        "POST", eb, ADMIN_TOKEN, json={"id_equipamento_modelo": mid, "numero_serie": f"SMK-{RUN_ID}-EXTRA"}), 201)
    e3 = r.json().get("id_os_equipamento")
    verifica("a visita aberta ganhou o 3o registro de servico", len(servicos_da_visita(os_id, vid, tok)) == 3)
    # remocao: sem conteudo e removido (204); com foto, bloqueado (409)
    if e3:
        expect("remover equipamento SEM conteudo -> 204", http("DELETE", f"{eb}/{e3}", ADMIN_TOKEN), 204)
        verifica("o registro de servico vazio desse equipamento tambem foi removido", len(servicos_da_visita(os_id, vid, tok)) == 2)

    # inicia a visita e fotografa o defeito de cada equipamento
    if not ida_completa(os_id, vid, tok, quiet=False) or not fotos_defeito_todas(os_id, vid, tok, quiet=False):
        return
    expect("remover equipamento que ja tem foto de defeito -> 409", http("DELETE", f"{eb}/{e2['id_os_equipamento']}", ADMIN_TOKEN), 409)
    r = expect("vincular novo equipamento apos as fotos -> 201", http(
        "POST", eb, ADMIN_TOKEN, json={"id_equipamento_modelo": mid, "numero_serie": f"SMK-{RUN_ID}-NOVO"}), 201)
    e4 = r.json().get("id_os_equipamento")
    est = estado_da_visita(os_id, vid, tok)
    verifica("estado: o equipamento novo (sem foto de defeito) volta a bloquear o inicio do atendimento",
             est.get("pode_iniciar_atendimento") is False and "NOVO" in (est.get("bloqueio_iniciar_atendimento") or ""), str(est)[:300])
    expect("iniciar atendimento com o novo equipamento sem foto -> 409", http(
        "POST", base(os_id, vid) + "/iniciar-atendimento", tok), 409)
    if e4:
        expect("remover o equipamento novo (ainda sem conteudo) -> 204", http("DELETE", f"{eb}/{e4}", ADMIN_TOKEN), 204)
    expect("iniciar atendimento (2 equipamentos, ambos com foto)", http("POST", base(os_id, vid) + "/iniciar-atendimento", tok), 200)

    # atendimento iniciado: o admin NAO edita mais o equipamento (409)
    expect("atendimento iniciado: vincular equipamento -> 409", http(
        "POST", eb, ADMIN_TOKEN, json={"id_equipamento_modelo": mid, "numero_serie": f"SMK-{RUN_ID}-TARDE"}), 409)
    expect("atendimento iniciado: corrigir serie -> 409", http(
        "PATCH", f"{eb}/{e2['id_os_equipamento']}", ADMIN_TOKEN, json={"numero_serie": serie2 + "-B"}), 409)
    expect("atendimento iniciado: remover equipamento -> 409", http("DELETE", f"{eb}/{e2['id_os_equipamento']}", ADMIN_TOKEN), 409)

    # a correcao de fotos/materiais so vale com a OS Finalizada
    sv = servicos_da_visita(os_id, vid, tok)
    if sv:
        sb = base(os_id, vid) + f"/servicos/{sv[0]['id_servico']}"
        expect("OS nao finalizada: admin PATCH de materiais -> 409", http("PATCH", sb, ADMIN_TOKEN, json={"materiais_utilizados": []}), 409)
        expect("OS nao finalizada: admin upload-foto -> 409", http(
            "POST", sb + "/upload-foto", ADMIN_TOKEN, files=arq_jpeg(), data={"tipo": "defeito"}), 409)
        expect("OS nao finalizada: admin DELETE de foto -> 409", http("DELETE", sb + "/fotos/1", ADMIN_TOKEN), 409)

    # a ultima OS com 1 equipamento nao perde o unico equipamento
    unica = nova_os(Ctx.cliente_id, None, "cenario7-unica")
    if unica is not None and unica.get("equipamentos"):
        r = expect("remover o ULTIMO equipamento da OS -> 409", http(
            "DELETE", f"/chamados/{unica['id_os']}/equipamentos/{unica['equipamentos'][0]['id_os_equipamento']}", ADMIN_TOKEN), 409)
        verifica("OS continua com seu equipamento", len(get_os(unica["id_os"]).get("equipamentos") or []) == 1)


# =====================================================================================================================
# j) Cenario 8 - OS Finalizada: o admin corrige fotos e materiais (custo recalculado, modelo/serie travados)
# =====================================================================================================================

def cenario_8_correcao_pos_finalizacao() -> None:
    if Ctx.os_final is None or Ctx.os_final_vid is None or not Ctx.os_final_servicos:
        P.pulou("cenario 8", "cenario 1 nao finalizou uma OS")
        return
    os_id, vid, sid = Ctx.os_final, Ctx.os_final_vid, Ctx.os_final_servicos[0]
    sb = base(os_id, vid) + f"/servicos/{sid}"
    eqs = get_os(os_id).get("equipamentos") or []

    # --- modelo/serie continuam travados (so fotos e materiais) ---
    if eqs:
        eb = f"/chamados/{os_id}/equipamentos"
        expect("OS Finalizada: corrigir serie -> 409", http("PATCH", f"{eb}/{eqs[0]['id_os_equipamento']}", ADMIN_TOKEN,
               json={"numero_serie": "OUTRA"}), 409)
        expect("OS Finalizada: trocar modelo -> 409", http("PATCH", f"{eb}/{eqs[0]['id_os_equipamento']}", ADMIN_TOKEN,
               json={"id_equipamento_modelo": Ctx.modelo2_id or Ctx.modelo_id}), 409)
        expect("OS Finalizada: vincular equipamento -> 409", http("POST", eb, ADMIN_TOKEN, json={
            "id_equipamento_modelo": Ctx.modelo_id, "numero_serie": f"POS-{RUN_ID}"}), 409)
        expect("OS Finalizada: remover equipamento -> 409", http("DELETE", f"{eb}/{eqs[0]['id_os_equipamento']}", ADMIN_TOKEN), 409)
    for corpo in ({"defeitos_principais": ["Refrigeração"]}, {"defeito_outros_descricao": "x"},
                  {"materiais_utilizados": [], "defeitos_principais": ["Refrigeração"]}, {}):
        expect(f"admin PATCH de servico com campo alem de materiais ({list(corpo) or 'vazio'}) -> 422",
               http("PATCH", sb, ADMIN_TOKEN, json=corpo), 422)

    # --- fotos: o admin envia/remove, nunca a ultima do tipo; tudo auditado ---
    fotos0 = http("GET", sb + "/fotos", ADMIN_TOKEN).json()
    n_def, n_con = len(fotos0.get("fotos_defeito") or []), len(fotos0.get("fotos_conserto") or [])
    r = expect("admin envia nova foto de conserto (960x1280) como correcao", http(
        "POST", sb + "/upload-foto", ADMIN_TOKEN, files=arq_conserto("correcao.jpg"), data={"tipo": "conserto"}), 200)
    nova = r.json().get("id_foto")
    expect("correcao continua exigindo 960x1280 no conserto: 300x200 -> 400", http(
        "POST", sb + "/upload-foto", ADMIN_TOKEN, files=arq_jpeg("peq.jpg", 300, 200), data={"tipo": "conserto"}), 400)
    r = expect("admin envia nova foto de defeito como correcao", http(
        "POST", sb + "/upload-foto", ADMIN_TOKEN, files=arq_jpeg("defeito_corr.jpg", 200, 150), data={"tipo": "defeito"}), 200)
    nova_def = r.json().get("id_foto")
    fotos1 = http("GET", sb + "/fotos", ADMIN_TOKEN).json()
    verifica("fotos aumentaram em 1 (conserto) e 1 (defeito)", len(fotos1.get("fotos_conserto") or []) == n_con + 1
             and len(fotos1.get("fotos_defeito") or []) == n_def + 1, str(fotos1)[:300])
    antigas = [f["id_foto"] for f in fotos1.get("fotos_conserto") or [] if f["id_foto"] != nova]
    if antigas:
        for fid in antigas:
            expect("admin remove foto de conserto antiga (ha outra do tipo) -> 204", http("DELETE", sb + f"/fotos/{fid}", ADMIN_TOKEN), 204)
    expect("admin remove a ULTIMA foto de conserto -> 409", http("DELETE", sb + f"/fotos/{nova}", ADMIN_TOKEN), 409)
    for fid in [f["id_foto"] for f in fotos1.get("fotos_defeito") or [] if f["id_foto"] != nova_def]:
        expect("admin remove foto de defeito excedente -> 204", http("DELETE", sb + f"/fotos/{fid}", ADMIN_TOKEN), 204)
    expect("admin remove a ULTIMA foto de defeito -> 409", http("DELETE", sb + f"/fotos/{nova_def}", ADMIN_TOKEN), 409)
    expect("admin remove foto inexistente -> 404", http("DELETE", sb + "/fotos/2147000000", ADMIN_TOKEN), 404)
    fotos2 = http("GET", sb + "/fotos", ADMIN_TOKEN).json()
    verifica("sobrou exatamente 1 foto de cada tipo", len(fotos2.get("fotos_defeito") or []) == 1
             and len(fotos2.get("fotos_conserto") or []) == 1, str(fotos2)[:300])
    expect("tecnico DELETE de foto -> 403", http("DELETE", sb + f"/fotos/{nova}", Ctx.tec1.token if Ctx.tec1 else None), 403)
    antes = custos(os_id)
    verifica("corrigir so fotos nao altera custo nem status",
             antes.get("congelado") is True and get_os(os_id).get("status") == "Finalizado"
             and abs((antes.get("custo_total_materiais") or 0) - (Ctx.os_final_materiais or 0)) < 0.01, str(antes)[:200])

    # --- materiais: custo RECALCULADO com os valores congelados (RN-33 / RN-49) ---
    congelados = antes.get("valores_utilizados")
    r = expect("admin corrige materiais do equipamento 1 (2 x Compressor R$ 850 + 3 x Filtro R$ 10)", http(
        "PATCH", sb, ADMIN_TOKEN, json={"materiais_utilizados": [
            {"nome": "Compressor 1/4 HP", "quantidade": 2, "valor": 850.00}, {"nome": "Filtro", "quantidade": 3, "valor": 10.00}]}), 200)
    verifica("servico devolve os materiais corrigidos", [m.get("nome") for m in r.json().get("materiais_utilizados") or []]
             == ["Compressor 1/4 HP", "Filtro"], r.resumo())
    depois = custos(os_id)
    verifica("custo continua congelado e com os MESMOS valores_utilizados (nao usa a configuracao atual)",
             depois.get("congelado") is True and depois.get("valores_utilizados") == congelados, str(depois.get("valores_utilizados"))[:200])
    # material do eq.1 passou de R$ 850 para R$ 1.730 (+ R$ 880): o total do snapshot sobe exatamente isso
    verifica("custo_total_materiais RECALCULADO (+ R$ 880,00)",
             abs((depois.get("custo_total_materiais") or 0) - ((antes.get("custo_total_materiais") or 0) + 880.0)) < 0.01,
             f"antes={antes.get('custo_total_materiais')} depois={depois.get('custo_total_materiais')}")
    verifica("total_geral subiu exatamente R$ 880,00",
             abs((depois.get("total_geral") or 0) - ((antes.get("total_geral") or 0) + 880.0)) < 0.01,
             f"antes={antes.get('total_geral')} depois={depois.get('total_geral')}")
    verifica("km, deslocamento, servico, pedagio e frete permanecem iguais",
             all(depois.get(c) == antes.get(c) for c in ("custo_total_km", "custo_total_deslocamento", "custo_total_servico",
                                                         "custo_total_pedagio", "custo_total_frete")), str(depois)[:300])
    verifica("a OS segue 'Finalizado'", get_os(os_id).get("status") == "Finalizado")
    Ctx.os_final_materiais = depois.get("custo_total_materiais")
    expect("tecnico PATCH de materiais da OS Finalizada -> 409", http(
        "PATCH", sb, Ctx.tec1.token if Ctx.tec1 else None, json={"materiais_utilizados": []}), 409)


# =====================================================================================================================
# k) Cenario 9 - sincronizacao offline (SDD 6.12): /sync/arquivos, /sync/eventos, /sync/minhas-os
# =====================================================================================================================

def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _sync_arquivo(token: str, os_id: int, vid: int, tipo: str, cfid: Optional[str] = None, size: Tuple[int, int] = (300, 200)) -> Tuple[str, Resp]:
    cfid = cfid or _uid()
    if tipo == "assinatura":
        arquivo = ("assinatura.png", png(200, 80), "image/png")
    else:
        arquivo = ("foto.jpg", jpeg(*size), "image/jpeg")
    r = http("POST", "/sync/arquivos", token, data={"client_file_id": cfid, "tipo_arquivo": tipo, "id_os": os_id, "id_visita": vid},
             files={"file": arquivo})
    return cfid, r


def _ev(os_id: int, vid: int, tipo: str, payload: Dict[str, Any], quando: datetime, cid: Optional[str] = None) -> Dict[str, Any]:
    return {"client_event_id": cid or _uid(), "tipo": tipo, "id_os": os_id, "id_visita": vid,
            "ocorrido_em": quando.isoformat(), "payload": payload}


def _enviar(token: str, eventos: List[Dict[str, Any]]) -> Resp:
    return http("POST", "/sync/eventos", token, json={"dispositivo_id": f"smoke-{RUN_ID}", "enviado_em": _agora().isoformat(),
                                                      "eventos": eventos})


def _res(r: Resp) -> List[Dict[str, Any]]:
    d = r.json()
    return d.get("resultados", []) if isinstance(d, dict) else []


def _cod(res: List[Dict[str, Any]]) -> List[Tuple[Any, Any]]:
    return [(x.get("resultado"), x.get("codigo")) for x in res]


def _os_sync(tec: Tecnico, rotulo: str, n_equip: int = 1) -> Optional[Tuple[int, int]]:
    os_ = nova_os(Ctx.cliente_id, tec.id, rotulo, n_equip=n_equip)  # type: ignore[arg-type]
    if os_ is None:
        return None
    vid = (os_.get("visitas") or [{}])[0].get("id_visita")
    if vid is None:
        P.falhou(f"OS {rotulo} sem visita automatica")
        return None
    return os_["id_os"], vid


def cenario_9_sincronizacao_offline() -> None:
    if Ctx.cliente_id is None or Ctx.modelo_id is None:
        P.pulou("cenario 9", "cliente/modelo de teste nao foram criados")
        return
    tec = novo_tecnico("tec-sync")
    if tec is None:
        return
    tok = tec.token or ""

    # --- permissoes basicas ---
    corpo_vazio = {"dispositivo_id": "d", "enviado_em": _agora().isoformat(), "eventos": []}
    expect("admin POST /sync/eventos -> 403 (so o tecnico sincroniza)", http("POST", "/sync/eventos", ADMIN_TOKEN, json=corpo_vazio), 403)
    expect("admin GET /sync/minhas-os -> 403", http("GET", "/sync/minhas-os", ADMIN_TOKEN), 403)
    expect("sem token POST /sync/eventos -> 401", http("POST", "/sync/eventos", json=corpo_vazio), 401)
    expect("lote vazio do tecnico -> 200", http("POST", "/sync/eventos", tok, json=corpo_vazio), 200)

    # --- /sync/arquivos: validacao, idempotencia, permissao ---
    a = _os_sync(tec, "cen9-arquivos")
    if a is None:
        return
    os_a, vid_a = a
    _, r = _sync_arquivo(tok, os_a, vid_a, "foto_conserto", size=(800, 600))
    expect("sync/arquivos: foto de conserto 800x600 -> 400 (resolucao insuficiente)", r, 400)
    cfid, r = _sync_arquivo(tok, os_a, vid_a, "foto_conserto", size=(1280, 960))
    expect("sync/arquivos: foto de conserto 1280x960 (paisagem) -> 200", r, 200)
    verifica("resultado 'aplicado' com url", r.json().get("resultado") == "aplicado" and bool(r.json().get("url")), r.resumo())
    url = r.json().get("url")
    _, r2 = _sync_arquivo(tok, os_a, vid_a, "foto_conserto", cfid=cfid, size=(1280, 960))
    expect("sync/arquivos: reenviar o MESMO client_file_id -> 200", r2, 200)
    verifica("reenvio devolve 'duplicado' com a MESMA url (idempotencia)",
             r2.json().get("resultado") == "duplicado" and r2.json().get("url") == url, r2.resumo())
    expect("sync/arquivos: foto de defeito pequena (40x30) -> 200 (defeito sem resolucao minima)",
           _sync_arquivo(tok, os_a, vid_a, "foto_defeito", size=(40, 30))[1], 200)
    expect("sync/arquivos: assinatura PNG -> 200", _sync_arquivo(tok, os_a, vid_a, "assinatura")[1], 200)
    expect("sync/arquivos: tipo_arquivo desconhecido -> 422", _sync_arquivo(tok, os_a, vid_a, "outro_tipo")[1], 422)
    if Ctx.tec1 and Ctx.tec1.token:
        expect("sync/arquivos: outro tecnico (OS que nao e dele) -> 403", _sync_arquivo(Ctx.tec1.token, os_a, vid_a, "foto_defeito")[1], 403)
        _, r3 = _sync_arquivo(Ctx.tec1.token, os_a, vid_a, "foto_defeito", cfid=cfid)
        expect("sync/arquivos: client_file_id ja usado por OUTRO tecnico -> 403", r3, 403)
    expect("sync/arquivos: admin -> 403", _sync_arquivo(ADMIN_TOKEN or "", os_a, vid_a, "foto_defeito")[1], 403)
    expect("sync/arquivos: PDF disfarcado de JPEG -> 422", http(
        "POST", "/sync/arquivos", tok, data={"client_file_id": _uid(), "tipo_arquivo": "foto_defeito", "id_os": os_a, "id_visita": vid_a},
        files={"file": ("a.jpg", b"%PDF-1.4 x", "image/jpeg")}), 422)
    expect("sync/arquivos: sem token -> 401", http(
        "POST", "/sync/arquivos", data={"client_file_id": _uid(), "tipo_arquivo": "foto_defeito", "id_os": os_a, "id_visita": vid_a},
        files={"file": ("a.jpg", jpeg(50, 50), "image/jpeg")}), 401)

    # --- fluxo completo offline ate Finalizado + reenvio do mesmo lote ---
    b = _os_sync(tec, "cen9-fluxo-completo")
    if b is None:
        return
    os_b, vid_b = b
    sv = servicos_da_visita(os_b, vid_b, tok)
    if len(sv) != 1:
        P.falhou("OS do fluxo offline sem o registro de servico esperado", str(sv)[:200])
        return
    sid = sv[0]["id_servico"]
    base_t = _agora() - timedelta(hours=3)  # tudo "aconteceu" 3 h antes do envio (aparelho offline)

    def m(min_: int) -> datetime:
        return base_t + timedelta(minutes=min_)

    f_ida = _sync_arquivo(tok, os_b, vid_b, "foto_deslocamento")[0]
    f_def = _sync_arquivo(tok, os_b, vid_b, "foto_defeito", size=(120, 90))[0]
    f_con = _sync_arquivo(tok, os_b, vid_b, "foto_conserto", size=(960, 1280))[0]
    f_ass = _sync_arquivo(tok, os_b, vid_b, "assinatura")[0]
    f_volta = _sync_arquivo(tok, os_b, vid_b, "foto_deslocamento")[0]
    eventos = [
        _ev(os_b, vid_b, "deslocamento_ida_iniciado", {"km_inicio": 1000, "foto_ref": f_ida}, m(0)),
        _ev(os_b, vid_b, "deslocamento_ida_finalizado", {"km_fim": 1020}, m(10)),
        _ev(os_b, vid_b, "foto_servico", {"id_servico": sid, "tipo": "defeito", "foto_ref": f_def}, m(12)),
        _ev(os_b, vid_b, "atendimento_iniciado", {}, m(15)),
        _ev(os_b, vid_b, "servico_salvo", {"id_servico": sid, "defeitos_principais": ["Refrigeração"],
                                           "materiais_utilizados": [MATERIAL_A]}, m(20)),
        _ev(os_b, vid_b, "foto_servico", {"id_servico": sid, "tipo": "conserto", "foto_ref": f_con}, m(25)),
        _ev(os_b, vid_b, "conserto_salvo", {"id_servico": sid}, m(30)),
        _ev(os_b, vid_b, "atendimento_finalizado", {"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO,
                                                    "assinatura_ref": f_ass}, m(40)),
        _ev(os_b, vid_b, "deslocamento_volta_iniciado", {"km_inicio": 1020}, m(50)),
        _ev(os_b, vid_b, "deslocamento_volta_finalizado", {"km_fim": 1040, "foto_ref": f_volta}, m(60)),
    ]
    r = expect("sync/eventos: lote com o fluxo completo (10 eventos) -> 200", _enviar(tok, eventos), 200)
    res = _res(r)
    verifica("os 10 eventos 'aplicado'", [x.get("resultado") for x in res] == ["aplicado"] * 10, str(_cod(res)))
    verifica("a resposta preserva a ordem de recebimento", [x.get("client_event_id") for x in res] == [e["client_event_id"] for e in eventos])
    os_final = get_os(os_b)
    verifica("OS chegou a 'Finalizado' com data_conclusao", os_final.get("status") == "Finalizado" and bool(os_final.get("data_conclusao")),
             f"status={os_final.get('status')}")
    v = (os_final.get("visitas") or [{}])[0]
    verifica("visita: finalizada, km_total=40, CPF so digitos, nome e assinatura gravados",
             v.get("servico_finalizado") is True and v.get("km_total") == 40 and v.get("documento_cliente") == "52998224725"
             and v.get("nome_cliente_assinatura") == "Maria Souza" and bool(v.get("assinatura_url")), str(v)[:300])
    try:
        ida = datetime.fromisoformat(str(v.get("ida_inicio_em")).replace("Z", "+00:00"))
        ida = ida if ida.tzinfo else ida.replace(tzinfo=timezone.utc)
        verifica("a visita grava o horario do APARELHO (3 h antes do envio), nao o do recebimento",
                 abs((ida - base_t).total_seconds()) < 60, f"ida_inicio_em={v.get('ida_inicio_em')} esperado~{base_t.isoformat()}")
    except Exception as exc:
        P.falhou("ler ida_inicio_em da visita sincronizada", f"{type(exc).__name__}: {exc} ({v.get('ida_inicio_em')})")
    cb = custos(os_b)
    verifica("custo congelado ao finalizar via sync (materiais R$ 850,00)", cb.get("congelado") is True
             and abs((cb.get("custo_total_materiais") or 0) - 850.0) < 0.01, str(cb)[:200])
    fotos_b = http("GET", base(os_b, vid_b) + f"/servicos/{sid}/fotos", ADMIN_TOKEN).json()
    verifica("fotos de defeito e conserto ligadas ao servico pelos eventos (foto_ref)",
             len(fotos_b.get("fotos_defeito") or []) == 1 and len(fotos_b.get("fotos_conserto") or []) == 1, str(fotos_b)[:200])

    res2 = _res(_enviar(tok, eventos))
    verifica("reenvio do MESMO lote -> todos 'duplicado' (idempotencia por client_event_id)",
             [x.get("resultado") for x in res2] == ["duplicado"] * 10, str(_cod(res2)))
    fotos_b2 = http("GET", base(os_b, vid_b) + f"/servicos/{sid}/fotos", ADMIN_TOKEN).json()
    verifica("reenvio nao duplicou fotos nem alterou o status", len(fotos_b2.get("fotos_defeito") or []) == 1
             and len(fotos_b2.get("fotos_conserto") or []) == 1 and get_os(os_b).get("status") == "Finalizado")

    # --- FOTO_DEFEITO_AUSENTE (TR-12) e CONSERTO_INCOMPLETO (TR-13) ---
    c = _os_sync(tec, "cen9-foto-ausente")
    if c is None:
        return
    os_c, vid_c = c
    sid_c = (servicos_da_visita(os_c, vid_c, tok) or [{}])[0].get("id_servico")
    bc = _agora() - timedelta(hours=2)
    evs = [
        _ev(os_c, vid_c, "deslocamento_ida_iniciado", {"km_inicio": 1}, bc),
        _ev(os_c, vid_c, "deslocamento_ida_finalizado", {"km_fim": 5}, bc + timedelta(minutes=5)),
        _ev(os_c, vid_c, "atendimento_iniciado", {}, bc + timedelta(minutes=10)),
        _ev(os_c, vid_c, "servico_salvo", {"id_servico": sid_c, "defeitos_principais": ["Refrigeração"]}, bc + timedelta(minutes=15)),
    ]
    res = _res(_enviar(tok, evs))
    verifica("atendimento_iniciado sem foto de defeito -> rejeitado FOTO_DEFEITO_AUSENTE; o seguinte, DEPENDENCIA_REJEITADA",
             _cod(res) == [("aplicado", None), ("aplicado", None), ("rejeitado", "FOTO_DEFEITO_AUSENTE"),
                           ("rejeitado", "DEPENDENCIA_REJEITADA")], str(_cod(res)))
    verifica("OS segue 'Agendado' (o atendimento nao foi iniciado)", get_os(os_c).get("status") == "Agendado")
    f_def_c = _sync_arquivo(tok, os_c, vid_c, "foto_defeito")[0]
    novos = [_ev(os_c, vid_c, "foto_servico", {"id_servico": sid_c, "tipo": "defeito", "foto_ref": f_def_c}, bc + timedelta(minutes=20)),
             _ev(os_c, vid_c, "atendimento_iniciado", {}, bc + timedelta(minutes=21))]
    res = _res(_enviar(tok, novos))
    verifica("apos enviar a foto, reenviar a acao com NOVO client_event_id -> aplicado", [x.get("resultado") for x in res] == ["aplicado", "aplicado"],
             str(_cod(res)))
    verifica("OS passou a 'Em Atendimento'", get_os(os_c).get("status") == "Em Atendimento")
    f_ass_c = _sync_arquivo(tok, os_c, vid_c, "assinatura")[0]
    ev_fim = _ev(os_c, vid_c, "atendimento_finalizado", {"nome_cliente": "Maria Souza", "documento_cliente": CPF_CLIENTE_VALIDO,
                                                         "assinatura_ref": f_ass_c}, _agora() - timedelta(minutes=5))
    res = _res(_enviar(tok, [ev_fim]))
    verifica("atendimento_finalizado sem conserto salvo/foto -> rejeitado CONSERTO_INCOMPLETO", _cod(res) == [("rejeitado", "CONSERTO_INCOMPLETO")],
             str(_cod(res)))
    res = _res(_enviar(tok, [_ev(os_c, vid_c, "tipo_que_nao_existe", {}, _agora() - timedelta(minutes=4))]))
    verifica("tipo de evento desconhecido -> rejeitado VALIDACAO", _cod(res) == [("rejeitado", "VALIDACAO")], str(_cod(res)))
    sem_fuso = _ev(os_c, vid_c, "atendimento_iniciado", {}, bc)
    sem_fuso["ocorrido_em"] = "2026-11-09T14:00:00"
    expect("evento com ocorrido_em SEM fuso -> 422 (lote inteiro)", _enviar(tok, [sem_fuso]), 422)

    # --- ARQUIVO_AUSENTE (transitorio) ---
    d_ = _os_sync(tec, "cen9-arquivo-ausente")
    if d_ is None:
        return
    os_d, vid_d = d_
    ausente = _uid()
    bd = _agora() - timedelta(hours=1)
    e1 = _ev(os_d, vid_d, "deslocamento_ida_iniciado", {"km_inicio": 7, "foto_ref": ausente}, bd)
    e2 = _ev(os_d, vid_d, "deslocamento_ida_finalizado", {"km_fim": 9}, bd + timedelta(minutes=5))
    res = _res(_enviar(tok, [e1, e2]))
    verifica("evento cujo arquivo ainda nao chegou -> rejeitado ARQUIVO_AUSENTE (e o seguinte da visita tambem)",
             _cod(res) == [("rejeitado", "ARQUIVO_AUSENTE"), ("rejeitado", "ARQUIVO_AUSENTE")], str(_cod(res)))
    vd = [x for x in get_os(os_d).get("visitas") or [] if x.get("id_visita") == vid_d]
    verifica("nada foi gravado (ARQUIVO_AUSENTE e transitorio)", bool(vd) and not vd[0].get("ida_inicio_em"), str(vd)[:200])
    expect("enviar o arquivo que faltava (mesmo client_file_id)", _sync_arquivo(tok, os_d, vid_d, "foto_deslocamento", cfid=ausente)[1], 200)
    res = _res(_enviar(tok, [e1, e2]))
    verifica("reenviar os MESMOS client_event_id agora -> aplicado", [x.get("resultado") for x in res] == ["aplicado", "aplicado"], str(_cod(res)))
    vd = [x for x in get_os(os_d).get("visitas") or [] if x.get("id_visita") == vid_d]
    verifica("ida iniciada e finalizada na visita (km 7 -> 9)", bool(vd) and vd[0].get("km_inicio_ida") == 7 and vd[0].get("km_fim_ida") == 9, str(vd)[:200])

    # --- minhas-os (cache local do app) ---
    r = expect("GET /sync/minhas-os (tecnico)", http("GET", "/sync/minhas-os", tok), 200)
    corpo = r.json() if isinstance(r.json(), dict) else {}
    itens = corpo.get("os") or []
    ids = [i.get("chamado", {}).get("id_os") for i in itens]
    verifica("traz sincronizado_em e as OS do tecnico (A, C e D)", bool(corpo.get("sincronizado_em"))
             and all(x in ids for x in (os_a, os_c, os_d)), f"ids={ids}")
    verifica("NAO traz OS de outro tecnico (a OS finalizada do tecnico 1)", Ctx.os_final not in ids, f"ids={ids}")
    item_c = next((i for i in itens if i.get("chamado", {}).get("id_os") == os_c), {})
    ch = item_c.get("chamado") or {}
    verifica("cada item traz equipamentos, visitas com servicos_realizados e estado_visita_vigente",
             len(ch.get("equipamentos") or []) == 1 and bool((ch.get("visitas") or [{}])[0].get("servicos_realizados"))
             and (item_c.get("estado_visita_vigente") or {}).get("visita_vigente") is True, str(item_c)[:300])
    expect("GET /sync/minhas-os?desde=... -> 200", http("GET", "/sync/minhas-os?desde=2026-01-01T00:00:00Z", tok), 200)

    # --- OS cancelada / reatribuida enquanto o aparelho estava offline ---
    e_ = _os_sync(tec, "cen9-cancelada")
    if e_ is not None:
        os_e, vid_e = e_
        ev = _ev(os_e, vid_e, "deslocamento_ida_iniciado", {"km_inicio": 1}, _agora() - timedelta(minutes=30))
        pre("cancelar a OS (preparacao)", http("POST", f"/chamados/{os_e}/cancelar", ADMIN_TOKEN, json={"motivo": "smoke offline"}))
        res = _res(_enviar(tok, [ev]))
        verifica("evento de OS cancelada pelo admin -> rejeitado OS_CANCELADA", _cod(res) == [("rejeitado", "OS_CANCELADA")], str(_cod(res)))
    f_ = _os_sync(tec, "cen9-reatribuida")
    tec_b = novo_tecnico("tec-sync-b")
    if f_ is not None and tec_b is not None:
        os_f, vid_f = f_
        ev = _ev(os_f, vid_f, "deslocamento_ida_iniciado", {"km_inicio": 1}, _agora() - timedelta(minutes=30))
        pre("reatribuir a OS a outro tecnico (preparacao)", http("PATCH", f"/chamados/{os_f}", ADMIN_TOKEN,
                                                                json={"id_tecnico_atribuido": tec_b.id}))
        res = _res(_enviar(tok, [ev]))
        verifica("evento de OS reatribuida a outro tecnico -> rejeitado OS_REATRIBUIDA", _cod(res) == [("rejeitado", "OS_REATRIBUIDA")], str(_cod(res)))


# =====================================================================================================================
# Execucao
# =====================================================================================================================

CENARIOS = [
    ("a) Autenticacao", cenario_a_autenticacao),
    ("b) Cadastros base (cliente, tecnicos e catalogo de modelos)", cenario_b_cadastros),
    ("c) Cenario 1 - fluxo normal completo (2 equipamentos, travas de foto/conserto)", cenario_1_fluxo_normal),
    ("d) Cenario 2 - pausa, reagendamento e novas exigencias de foto", cenario_2_pausa_reagendamento),
    ("e) Cenario 3 - cancelamento", cenario_3_cancelamento),
    ("f) Cenario 4 - permissoes (RBAC)", cenario_4_permissoes),
    ("g) Cenario 5 - desativacao do tecnico (RN-08a)", cenario_5_desativacao),
    ("h) Cenario 6 - uploads", cenario_6_uploads),
    ("i) Cenario 7 - equipamentos da OS: edicao do admin ate o inicio do atendimento", cenario_7_equipamentos_admin),
    ("j) Cenario 8 - OS Finalizada: correcao de fotos e materiais pelo admin", cenario_8_correcao_pos_finalizacao),
    ("k) Cenario 9 - sincronizacao offline (/api/sync)", cenario_9_sincronizacao_offline),
]


def lista_sql(ids: List[int]) -> str:
    return ", ".join(map(str, sorted(ids))) if ids else "NULL"


def imprimir_relatorio() -> None:
    print("\n" + "=" * 78)
    print("RESUMO")
    print("=" * 78)
    for nome, (ok, ko, sk) in P.por_cenario.items():
        marca = OK if ko == 0 else KO
        print(f"  {marca} {nome}: {ok} ok, {ko} falha(s), {sk} pulado(s)")
    total_falhas = len(P.falhas)
    print(f"\nTOTAL: {P.ok} passos OK, {total_falhas} FALHA(S), {len(P.pulados)} pulado(s)")
    if P.falhas:
        print("\nFalhas:")
        for f in P.falhas:
            print(f"  {KO} {f}")
    if P.pulados:
        print("\nPulados:")
        for f in P.pulados:
            print(f"  {SKIP} {f}")

    print("\n" + "-" * 78)
    print(f"DADOS CRIADOS NESTA EXECUCAO (RUN_ID={RUN_ID}; prefixo '{PREFIXO}')")
    print("-" * 78)
    print(f"  Clientes (id_cliente):                  {sorted(CRIADOS['clientes'])}")
    print(f"  Tecnicos (id_tecnico):                  {sorted(CRIADOS['tecnicos'])}")
    print(f"  Modelos  (id_equipamento_modelo):       {sorted(CRIADOS['modelos'])}")
    print(f"  OS       (id_os):                       {sorted(CRIADOS['os'])}")
    print("  Obs.: tecnicos desativados pelo cenario 5 continuam na tabela (desativacao logica).")
    print("  Obs.: modelos de equipamento nunca sao excluidos pela API (so desativados); a limpeza e por SQL.")
    print("  Obs.: arquivos enviados ficam no disco do servidor da API (static/uploads e static/assinaturas).")

    os_ids, tec_ids, cli_ids = lista_sql(CRIADOS["os"]), lista_sql(CRIADOS["tecnicos"]), lista_sql(CRIADOS["clientes"])
    mod_ids = lista_sql(CRIADOS["modelos"])
    srv = f"SELECT id_servico FROM servico_equipamento WHERE id_visita IN (SELECT id_visita FROM visita WHERE id_os IN ({os_ids}))"
    print("\n" + "-" * 78)
    print("SQL DE LIMPEZA SUGERIDO (TEXTO; o script NAO executa nada. Revise e rode voce mesmo no SQL Editor)")
    print("-" * 78)
    print(f"""-- 0) Conferencia (somente leitura)
SELECT id_os, status, is_cancelled, id_tecnico_atribuido FROM ordem_servico WHERE id_os IN ({os_ids});
SELECT id_tecnico, nome, email, is_active FROM tecnico WHERE id_tecnico IN ({tec_ids}) AND nome LIKE '{PREFIXO}%';
SELECT id_cliente, razao_social FROM cliente WHERE id_cliente IN ({cli_ids}) AND razao_social LIKE '{PREFIXO}%';
SELECT id_equipamento_modelo, modelo, is_active FROM equipamento_modelo WHERE id_equipamento_modelo IN ({mod_ids}) AND modelo LIKE '{PREFIXO}%';
SELECT id_os, id_os_equipamento, id_equipamento_modelo, numero_serie FROM os_equipamento WHERE id_os IN ({os_ids});
SELECT resultado, codigo, count(*) FROM sync_evento WHERE id_os IN ({os_ids}) GROUP BY resultado, codigo;
SELECT tipo_arquivo, count(*) FROM sync_arquivo WHERE id_os IN ({os_ids}) GROUP BY tipo_arquivo;
-- (anote antes: SELECT assinatura_url FROM visita WHERE id_os IN ({os_ids}); e SELECT url FROM sync_arquivo WHERE id_os IN ({os_ids}); para apagar os arquivos do disco)

-- 1) Remocao (ordem respeita as FKs: servico_equipamento antes de os_equipamento; sync_* antes de visita;
--    os_equipamento antes de equipamento_modelo). Troque COMMIT por ROLLBACK para um ensaio.
BEGIN;
DELETE FROM material            WHERE id_servico IN ({srv});
DELETE FROM servico_foto        WHERE id_servico IN ({srv});
DELETE FROM servico_defeito     WHERE id_servico IN ({srv});
DELETE FROM servico_equipamento WHERE id_visita IN (SELECT id_visita FROM visita WHERE id_os IN ({os_ids}));
DELETE FROM comprovante         WHERE id_visita IN (SELECT id_visita FROM visita WHERE id_os IN ({os_ids}));
DELETE FROM pausa               WHERE visita_id IN (SELECT id_visita FROM visita WHERE id_os IN ({os_ids}));
DELETE FROM sync_evento         WHERE id_os IN ({os_ids}) OR id_tecnico IN ({tec_ids});
DELETE FROM sync_arquivo        WHERE id_os IN ({os_ids}) OR id_tecnico IN ({tec_ids});
DELETE FROM log_acao            WHERE id_os IN ({os_ids}) OR id_usuario IN ({tec_ids})
                                   OR (id_os IS NULL AND acao LIKE 'EQUIPAMENTO_MODELO_%' AND CAST(payload AS TEXT) LIKE '%{PREFIXO}%');
DELETE FROM custo_os            WHERE id_os IN ({os_ids});
DELETE FROM visita              WHERE id_os IN ({os_ids});
DELETE FROM os_equipamento      WHERE id_os IN ({os_ids});
DELETE FROM ordem_servico       WHERE id_os IN ({os_ids});
DELETE FROM equipamento_modelo  WHERE id_equipamento_modelo IN ({mod_ids}) AND modelo LIKE '{PREFIXO}%';
DELETE FROM tecnico             WHERE id_tecnico IN ({tec_ids}) AND nome LIKE '{PREFIXO}%';
DELETE FROM cliente             WHERE id_cliente IN ({cli_ids}) AND razao_social LIKE '{PREFIXO}%';
COMMIT;""")


def main() -> int:
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        return _abortar("defina ADMIN_EMAIL e ADMIN_PASSWORD (e, opcionalmente, BASE_URL) nas variaveis de ambiente")
    print(f"Fast Ariam - smoke test da API  |  alvo: {API}  |  RUN_ID={RUN_ID}")
    print("ATENCAO: este script ESCREVE no banco da API alvo (dev = producao no mesmo Supabase). Nada e apagado.")
    try:
        r = client.get("/auth/me")  # qualquer rota: so para saber se a API responde
    except httpx.HTTPError as exc:
        return _abortar(f"API inacessivel em {API} ({type(exc).__name__}: {exc})")
    if r.status_code not in (200, 401, 403):
        return _abortar(f"resposta inesperada de {API}/auth/me: HTTP {r.status_code}. A URL esta correta?")

    for nome, fn in CENARIOS:
        etapa(nome)
        P.cenario = nome
        try:
            fn()
        except SystemExit as exc:
            return int(exc.code) if isinstance(exc.code, int) else 2
        except Exception as exc:  # um cenario quebrado nao impede os demais
            P.falhou("excecao inesperada no cenario", f"{type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
    imprimir_relatorio()
    return 1 if P.falhas else 0


if __name__ == "__main__":
    code = main()
    sys.exit(code)
