"""Helpers (não-fixtures) dos testes de OS/visitas: usuários, imagens e driver de fluxo."""
import base64
import itertools
from dataclasses import dataclass
from io import BytesIO
from datetime import date, timedelta
from typing import Optional

from fastapi.testclient import TestClient
from PIL import Image

from app.core.security import create_access_token, hash_password
from app.models.chamado import OrdemServico
from app.models.cliente import Cliente
from app.models.tecnico import Tecnico

_seq = itertools.count(1)


# --- Dados ------------------------------------------------------------------------------------------------------------
@dataclass
class Usuario:
    id: int
    email: str
    role: str
    headers: dict


def _headers(user_id: int, email: str, role: str) -> dict:
    token = create_access_token({"sub": email, "user_id": user_id, "role": role})
    return {"Authorization": f"Bearer {token}"}


def criar_usuario(db, role: str = "tecnico", ativo: bool = True) -> Usuario:
    n = next(_seq)
    t = Tecnico(nome=f"Usuario {n}", cpf=f"{n:011d}", cnpj=f"{n:014d}", email=f"u{n}@teste.com",
                telefone="27999999999", password_hash=hash_password("Senha@12345"), role=role, is_active=ativo)
    db.add(t)
    db.commit()
    db.refresh(t)
    return Usuario(t.id_tecnico, t.email, role, _headers(t.id_tecnico, t.email, role))


def criar_cliente(db, ativo: bool = True) -> int:
    n = next(_seq)
    c = Cliente(razao_social=f"Cliente {n}", codigo=10000 + n, uf="ES", is_active=ativo)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c.id_cliente


# --- Imagens ----------------------------------------------------------------------------------------------------------
def imagem(largura: int, altura: int, formato: str = "JPEG") -> tuple:
    img = Image.new("RGB", (largura, altura), color="red")
    buf = BytesIO()
    img.save(buf, format=formato)
    ext, mime = ("jpg", "image/jpeg") if formato == "JPEG" else ("png", "image/png")
    return (f"foto_{largura}x{altura}.{ext}", buf.getvalue(), mime)


def assinatura_b64(com_prefixo: bool = True) -> str:
    img = Image.new("RGB", (200, 80), color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}" if com_prefixo else b64


CPF_VALIDO = "529.982.247-25"
CPF_VALIDO_DIGITOS = "52998224725"


# --- Driver do fluxo --------------------------------------------------------------------------------------------------
class Fluxo:
    """Atalhos HTTP para conduzir uma OS/visita pelo fluxo completo."""

    def __init__(self, client: TestClient, admin: Usuario, tecnico: Usuario, cliente_id: int):
        self.c = client
        self.admin = admin
        self.tecnico = tecnico
        self.cliente_id = cliente_id
        self.os_id: Optional[int] = None
        self.visita_id: Optional[int] = None
        self._modelo_id: Optional[int] = None

    # ---- Catálogo / equipamentos (v0.5) ----
    def criar_modelo(self, nome: Optional[str] = None) -> int:
        """Cria um modelo no catálogo (admin) e devolve o id."""
        nome = nome or f"Freezer vertical modelo T{next(_seq)}"
        r = self.c.post("/api/equipamentos/", json={"modelo": nome}, headers=self.admin.headers)
        assert r.status_code == 201, r.text
        return r.json()["id_equipamento_modelo"]

    def novos_equipamentos(self, n: int = 1) -> list:
        """`n` equipamentos (mesmo modelo, séries diferentes) no formato de `ChamadoCreate.equipamentos`."""
        if self._modelo_id is None:
            self._modelo_id = self.criar_modelo()
        return [{"id_equipamento_modelo": self._modelo_id, "numero_serie": f"FZ-{next(_seq):05d}"} for _ in range(n)]

    # ---- OS ----
    def criar_os(self, com_tecnico: bool = True, equipamentos: Optional[list] = None, n_equipamentos: int = 1,
                 **extra) -> dict:
        body = {"id_cliente": self.cliente_id, "descricao_cliente": "Gôndola não gela",
                "equipamentos": equipamentos if equipamentos is not None else self.novos_equipamentos(n_equipamentos),
                **extra}
        if com_tecnico:
            body["id_tecnico_atribuido"] = self.tecnico.id
        r = self.c.post("/api/chamados/", json=body, headers=self.admin.headers)
        assert r.status_code == 201, r.text
        self.os_id = r.json()["id_os"]
        return r.json()

    def criar_visita(self, data_visita: Optional[str] = None, **extra) -> dict:
        """
        Desde o D1, toda OS Agendado ja nasce com UMA visita aberta (criada na mesma transacao). Este helper
        reutiliza essa visita; se `data_visita`/`extra` forem informados, o admin os aplica por PATCH.
        """
        abertas = [v for v in self.os()["visitas"] if not v["servico_finalizado"]]
        assert abertas, "a OS deveria ter uma visita aberta"
        visita = abertas[-1]
        self.visita_id = visita["id_visita"]
        corpo = dict(extra)
        if data_visita and data_visita != visita["data_visita"]:
            corpo["data_visita"] = data_visita
        if corpo:
            r = self.c.patch(f"/api/chamados/{self.os_id}/visitas/{self.visita_id}", json=corpo,
                             headers=self.admin.headers)
            assert r.status_code == 200, r.text
            visita = r.json()
        return visita

    def os(self, headers=None) -> dict:
        r = self.c.get(f"/api/chamados/{self.os_id}", headers=headers or self.admin.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def url(self, sufixo: str) -> str:
        return f"/api/chamados/{self.os_id}/visitas/{self.visita_id}/{sufixo}"

    def post(self, sufixo: str, json=None, headers=None, **kw):
        return self.c.post(self.url(sufixo), json=json, headers=headers or self.tecnico.headers, **kw)

    # ---- etapas ----
    def foto_deslocamento(self, tipo: str, momento: str, headers=None, size=(300, 200)):
        return self.c.post(self.url("upload-deslocamento"), headers=headers or self.tecnico.headers,
                           data={"tipo": tipo, "momento": momento}, files={"file": imagem(*size)})

    def iniciar(self, tipo: str, km: int, **extra):
        return self.post("iniciar-deslocamento", {"tipo": tipo, "km_inicio": km, **extra})

    def finalizar(self, tipo: str, km: int, **extra):
        return self.post("finalizar-deslocamento", {"tipo": tipo, "km_fim": km, **extra})

    def ida_completa(self, km_ini: int = 1000, km_fim: int = 1020):
        assert self.iniciar("ida", km_ini).status_code == 200
        assert self.foto_deslocamento("ida", "inicio").status_code == 200
        assert self.finalizar("ida", km_fim).status_code == 200

    def iniciar_atendimento(self, completar: bool = True, **extra):
        """`completar=True` (padrão) registra antes a foto de defeito de cada equipamento (melhor esforço, TR-12)."""
        if completar:
            self.fotos_defeito_todas(estrito=False)
        return self.post("iniciar-atendimento", extra or {})

    def pausar(self, motivo: str = "Peça pendente", descricao: Optional[str] = None, headers=None, **extra):
        body = {"motivo": motivo, **extra}
        if descricao is not None:
            body["descricao"] = descricao
        return self.post("pausar", body, headers=headers)

    def finalizar_atendimento(self, cpf: str = CPF_VALIDO, nome: str = "Maria Gerente", assinatura=None,
                              completar: bool = True, **extra):
        if completar:
            self.conserto_completo()
        return self.post("finalizar-atendimento", {
            "nome_cliente": nome, "documento_cliente": cpf,
            "assinatura_base64": assinatura if assinatura is not None else assinatura_b64(), **extra})

    def volta_completa(self, km_ini: int = 1020, km_fim: int = 1040, foto_fim: bool = True):
        assert self.iniciar("volta", km_ini).status_code == 200
        if foto_fim:
            assert self.foto_deslocamento("volta", "fim").status_code == 200
        return self.finalizar("volta", km_fim)

    # ---- serviço por equipamento (v0.5: o registro é criado pelo servidor; o técnico só o preenche) ----
    def servicos(self, headers=None, estrito: bool = True) -> list:
        r = self.c.get(self.url("servicos"), headers=headers or self.tecnico.headers)
        if not estrito and r.status_code != 200:
            return []
        assert r.status_code == 200, r.text
        return r.json()

    def servico(self, materiais=None, indice: int = 0, headers=None, **extra):
        """PATCH do registro de serviço do `indice`-ésimo equipamento da OS (defeito principal padrão)."""
        servico_id = self.servicos()[indice]["id_servico"]
        body = {"defeitos_principais": ["Refrigeração"], **extra}
        if materiais is not None:  # sem `materiais`, não mexe nos materiais já lançados
            body["materiais_utilizados"] = materiais
        return self.c.patch(self.url(f"servicos/{servico_id}"), json=body, headers=headers or self.tecnico.headers)

    def foto_servico(self, tipo: str, indice: int = 0, size=None, headers=None):
        servico_id = self.servicos()[indice]["id_servico"]
        size = size or ((960, 1280) if tipo == "conserto" else (300, 200))
        return self.c.post(self.url(f"servicos/{servico_id}/upload-foto"), headers=headers or self.tecnico.headers,
                           data={"tipo": tipo}, files={"file": imagem(*size)})

    def fotos_defeito_todas(self, estrito: bool = True):
        """
        Foto de defeito de TODOS os equipamentos da OS (pré-condição de iniciar o atendimento, TR-12). Com
        `estrito=False` é "melhor esforço": não afirma nada (o servidor decide e testes de falha seguem falhando).
        """
        for i in range(len(self.servicos(estrito=estrito))):
            r = self.foto_servico("defeito", i)
            if estrito:
                assert r.status_code == 200, r.text

    def salvar_conserto(self, indice: int = 0, headers=None):
        servico_id = self.servicos()[indice]["id_servico"]
        return self.c.post(self.url(f"servicos/{servico_id}/salvar-conserto"), json={},
                           headers=headers or self.tecnico.headers)

    def conserto_completo(self, estrito: bool = False):
        """
        Defeito + "Salvar conserto" + foto de conserto de TODOS os equipamentos (pré-condição de finalizar, TR-13).
        Por padrão é "melhor esforço" (não afirma nada): o servidor decide, e testes de falha continuam falhando
        do jeito esperado. Com `estrito=True` exige sucesso.
        """
        for i in range(len(self.servicos(estrito=estrito))):
            for resp in (self.servico(indice=i), self.salvar_conserto(i), self.foto_servico("conserto", i)):
                if estrito:
                    assert resp.status_code == 200, resp.text

    def estado(self, headers=None) -> dict:
        r = self.c.get(self.url("estado"), headers=headers or self.tecnico.headers)
        assert r.status_code == 200, r.text
        return r.json()

    def ate_em_atendimento(self):
        self.criar_os()
        self.criar_visita()
        self.ida_completa()
        self.fotos_defeito_todas()
        r = self.iniciar_atendimento(completar=False)
        assert r.status_code == 200, r.text
        return self


def db_os(db, os_id: int) -> OrdemServico:
    db.expire_all()
    return db.get(OrdemServico, os_id)


def futuro(dias: int = 10) -> str:
    """Data ISO futura (os testes nao podem depender de datas fixas: reagendar recusa data passada)."""
    return (date.today() + timedelta(days=dias)).isoformat()
