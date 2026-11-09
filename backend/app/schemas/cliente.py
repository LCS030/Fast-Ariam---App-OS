import re
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Limites alinhados às colunas de `cliente` (SDD 4.2): evitam erro de banco (500) por texto longo demais.
_INT4_MAX = 2147483647


def _texto(max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length)


RazaoSocial = Annotated[str, _texto(100)]
TelefoneCli = Annotated[str, _texto(20)]
Endereco = Annotated[str, _texto(200)]
Numero = Annotated[str, _texto(20)]
Bairro = Annotated[str, _texto(100)]
Cidade = Annotated[str, _texto(100)]
ContatoNome = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ContatoTelefone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]

_UF_RE = re.compile(r"^[A-Z]{2}$")


def validar_uf(valor: str) -> str:
    """UF com exatamente 2 letras (SDD 7). Entrada em minúsculas é normalizada para maiúsculas."""
    uf = (valor or "").strip().upper()
    if not _UF_RE.fullmatch(uf):
        raise ValueError("UF deve ter exatamente 2 letras maiúsculas (ex.: ES).")
    return uf


# noinspection PyArgumentList
class ClienteBase(BaseModel):
    """
    Campos de ENTRADA do cadastro de cliente (SDD 6.4): razao_social, telefone, endereco, numero, bairro, cidade,
    uf (2 letras) e `codigo` (inteiro, único) são obrigatórios. Contato principal é opcional.
    """
    razao_social: RazaoSocial = Field(..., examples=["AUTO SERVIÇO JONAS LTDA"])
    contato_principal_nome: Optional[ContatoNome] = Field(None, examples=["Sylvia Rodrigues"])
    contato_principal_telefone: Optional[ContatoTelefone] = Field(None, examples=["46165375212"])
    telefone: TelefoneCli = Field(..., examples=["6574653211"])
    endereco: Endereco = Field(..., examples=["PRACA JOAO APARECIDO"])
    numero: Numero = Field(..., examples=["354"])
    bairro: Bairro = Field(..., examples=["CENTRO"])
    cidade: Cidade = Field(..., examples=["SERRA"])
    uf: str = Field(..., examples=["ES"])
    codigo: int = Field(..., ge=1, le=_INT4_MAX, examples=[55835],
                        description="Código do cliente (vem de outro sistema), informado pelo administrador. Único.")
    is_active: bool = True

    @field_validator("uf", mode="after")
    @classmethod
    def _uf_valida(cls, valor: str) -> str:
        return validar_uf(valor)


class ClienteCreate(ClienteBase):
    pass


class Cliente(BaseModel):
    """
    Saída. Os campos de endereço/telefone são tolerantes a registros antigos incompletos (colunas anuláveis no banco),
    para que a listagem não falhe com 500; a ENTRADA continua estrita (ClienteCreate).
    """
    model_config = ConfigDict(from_attributes=True)

    id_cliente: int
    razao_social: str
    contato_principal_nome: Optional[str] = None
    contato_principal_telefone: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None
    numero: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    uf: str
    codigo: int
    is_active: bool = True


class ClienteUpdate(BaseModel):
    """PATCH parcial. Campos obrigatórios no banco não aceitam `null` explícito (evita erro 500 por NOT NULL)."""
    razao_social: Optional[RazaoSocial] = None
    contato_principal_nome: Optional[ContatoNome] = None
    contato_principal_telefone: Optional[ContatoTelefone] = None
    telefone: Optional[TelefoneCli] = None
    endereco: Optional[Endereco] = None
    numero: Optional[Numero] = None
    bairro: Optional[Bairro] = None
    cidade: Optional[Cidade] = None
    uf: Optional[str] = None
    codigo: Optional[int] = Field(None, ge=1, le=_INT4_MAX)
    is_active: Optional[bool] = None

    @field_validator("razao_social", "telefone", "endereco", "numero", "bairro", "cidade", "uf", "codigo", "is_active",
                     mode="after")
    @classmethod
    def _obrigatorios_nao_nulos(cls, valor):
        if valor is None:
            raise ValueError("Este campo não pode ser nulo.")
        return valor

    @field_validator("uf", mode="after")
    @classmethod
    def _uf_valida(cls, valor: str) -> str:
        return validar_uf(valor)
