import re
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, StringConstraints, field_validator

from app.core.validators import validar_cpf
from app.schemas.token import validar_forca_senha
from .base_schemas import UserRole

# Limites alinhados às colunas de `tecnico` (SDD 4.1): evitam erro de banco (500) por texto longo demais.
def Texto(max_length: int) -> StringConstraints:
    """Texto obrigatório: sem espaços nas pontas, não vazio, com tamanho máximo da coluna."""
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


Nome = Annotated[str, Texto(100)]
Cnpj = Annotated[str, Texto(30)]  # aceita com ou sem máscara; normalizado (18 caracteres) pelo validador
Cpf = Annotated[str, Texto(20)]  # aceita com ou sem máscara; normalizado (14 caracteres) pelo validador
InscricaoEstadual = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
Telefone = Annotated[str, Texto(20)]
Email = EmailStr  # normalizado para minúsculas; no máximo 100 caracteres (coluna email)


# --- Validação/normalização de documentos ------------------------------------------------------------------------------
# Decisão (registrada no relatório): CPF e CNPJ de técnico são validados (dígitos verificadores) e gravados na forma
# canônica COM máscara (CPF 14 e CNPJ 18 caracteres = largura das colunas, e formato dos dados existentes). A forma
# única garante que a UNIQUE de `cnpj` (RN-06) não seja contornada por "00000000000100" vs "00.000.000/0001-00".
# (A visita guarda o CPF do cliente só com dígitos; isso é outra coluna, regra do Backend A.)

def normalizar_cnpj(valor: str) -> str:
    return re.sub(r"\D", "", valor or "")


def cnpj_valido(valor: str) -> bool:
    """CNPJ válido: 14 dígitos, não repetidos, dígitos verificadores corretos."""
    cnpj = normalizar_cnpj(valor)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    for tamanho in (12, 13):
        pesos = ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if tamanho == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
        soma = sum(int(cnpj[i]) * pesos[i] for i in range(tamanho))
        resto = soma % 11
        digito = 0 if resto < 2 else 11 - resto
        if digito != int(cnpj[tamanho]):
            return False
    return True


def formatar_cpf(valor: str) -> str:
    """Valida e devolve o CPF no formato 000.000.000-00. Levanta ValueError("CPF inválido")."""
    d = validar_cpf(valor)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def formatar_cnpj(valor: str) -> str:
    """Valida e devolve o CNPJ no formato 00.000.000/0000-00. Levanta ValueError("CNPJ inválido")."""
    if not cnpj_valido(valor):
        raise ValueError("CNPJ inválido")
    d = normalizar_cnpj(valor)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def _exigir_nao_nulo(valor):
    if valor is None:
        raise ValueError("Este campo não pode ser nulo.")
    return valor


class DadosBancarios(BaseModel):
    """Dados bancários no cadastro (RN-07): banco, agência e conta obrigatórios; Pix opcional."""
    banco: Annotated[str, Texto(100)]
    agencia: Annotated[str, Texto(50)]
    conta: Annotated[str, Texto(50)]
    pix: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None


class DadosBancariosResposta(BaseModel):
    """
    Saída (SOMENTE admin, SEG-10). Tolerante a registros antigos incompletos, para a listagem não falhar (500).
    Nenhum schema de resposta destinado ao técnico (ex.: /auth/me) inclui este modelo.
    """
    banco: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None
    pix: Optional[str] = None


class _TecnicoCampos(BaseModel):
    @field_validator("email", mode="after", check_fields=False)
    @classmethod
    def _email_minusculo(cls, valor):
        if isinstance(valor, str):
            valor = valor.strip().lower()
            if len(valor) > 100:
                raise ValueError("O e-mail deve ter no máximo 100 caracteres.")
        return valor


class TecnicoBase(_TecnicoCampos):
    """
    Campos de ENTRADA do cadastro (SDD 6.3.1): nome, cnpj, cpf, email, telefone e dados_bancarios são obrigatórios.

    Decisão: o diff não commitado que tornava telefone/dados_bancarios opcionais foi REVERTIDO para a entrada, pois
    contradiz SDD 6.3.1/7 e PRD RN-07. A tolerância a registros antigos incompletos (que motivou o diff: listar o admin
    do seed gerava erro de validação na resposta) fica no schema de SAÍDA `Tecnico`, que é separado.
    """
    cnpj: Cnpj
    inscricao_estadual: Optional[InscricaoEstadual] = None
    nome: Nome
    cpf: Cpf
    telefone: Telefone
    email: Email
    dados_bancarios: DadosBancarios
    is_active: bool = True
    role: UserRole = UserRole.TECNICO

    @field_validator("cpf", mode="after")
    @classmethod
    def _cpf_valido(cls, valor: str) -> str:
        return formatar_cpf(valor)

    @field_validator("cnpj", mode="after")
    @classmethod
    def _cnpj_valido(cls, valor: str) -> str:
        return formatar_cnpj(valor)


class TecnicoCreate(TecnicoBase):
    password: str

    @field_validator("password")
    @classmethod
    def _senha_valida(cls, valor: str) -> str:
        return validar_forca_senha(valor)


class Tecnico(BaseModel):
    """
    Saída administrativa (GET/POST/PATCH em /api/tecnicos). Nunca contém `password_hash`.
    Inclui dados bancários: só o administrador acessa estas rotas (SEG-10).
    """
    model_config = ConfigDict(from_attributes=True)

    id_tecnico: int
    cnpj: str
    inscricao_estadual: Optional[str] = None
    nome: str
    cpf: str
    telefone: Optional[str] = None
    email: str
    dados_bancarios: Optional[DadosBancariosResposta] = None
    is_active: bool = True
    role: UserRole = UserRole.TECNICO


class UsuarioAtual(BaseModel):
    """
    Saída de GET /api/auth/me (SDD 6.2 / PR-06). Seguro para o técnico: SEM dados bancários, CPF, CNPJ ou telefone.
    """
    model_config = ConfigDict(from_attributes=True)

    id_tecnico: int
    nome: str
    email: str
    role: UserRole
    is_active: bool


class DadosBancariosUpdate(BaseModel):
    """Atualização parcial dos dados bancários (somente admin, RN-07). banco/agência/conta não podem ser esvaziados."""
    banco: Optional[Annotated[str, Texto(100)]] = None
    agencia: Optional[Annotated[str, Texto(50)]] = None
    conta: Optional[Annotated[str, Texto(50)]] = None
    pix: Optional[Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]] = None

    @field_validator("banco", "agencia", "conta", mode="after")
    @classmethod
    def _obrigatorios_nao_nulos(cls, valor):
        return _exigir_nao_nulo(valor)


class TecnicoUpdate(_TecnicoCampos):
    """PATCH parcial. Campos obrigatórios no banco não aceitam `null` explícito (evita erro 500 por NOT NULL)."""
    cnpj: Optional[Cnpj] = None
    cpf: Optional[Cpf] = None
    inscricao_estadual: Optional[InscricaoEstadual] = None
    nome: Optional[Nome] = None
    telefone: Optional[Telefone] = None
    email: Optional[Email] = None
    dados_bancarios: Optional[DadosBancariosUpdate] = None
    is_active: Optional[bool] = None
    role: Optional[UserRole] = None

    @field_validator("cnpj", "cpf", "nome", "telefone", "email", "dados_bancarios", "is_active", "role", mode="after")
    @classmethod
    def _campos_obrigatorios_nao_nulos(cls, valor):
        return _exigir_nao_nulo(valor)

    @field_validator("cpf", mode="after")
    @classmethod
    def _cpf_valido(cls, valor: str) -> str:
        return formatar_cpf(valor)

    @field_validator("cnpj", mode="after")
    @classmethod
    def _cnpj_valido(cls, valor: str) -> str:
        return formatar_cnpj(valor)


"""
Ponto de atenção:
    No documento 'Dados para cadastro e instrução tecnica' é dito sobre a inclusão dos dados bancários da conta jurídica
    para pagamento e a menção do número da OS no corpo da nota. Isso é responsabilidade do técnico na hora que ele emite
    a nota fiscal dele. 
"""
