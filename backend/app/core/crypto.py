"""
Confidencialidade em repouso: AES-256-GCM no código da aplicação (autenticado: adulteração => falha, nunca dado errado).

  * `TextoCifrado`   -> tipo SQLAlchemy: cifra ao gravar e decifra ao ler. Formato guardado: "enc1:" + base64(nonce||ct||tag).
  * `cifrar_bytes`   -> arquivos (assinatura em disco).
  * `indice_cego`    -> HMAC-SHA256 determinístico para buscar/garantir unicidade sem guardar o valor em claro.

Decisões (ver SDD, seção de segurança):
  * Nonce de 96 bits aleatório e novo a cada cifragem (nunca reutilizado com a mesma chave).
  * AAD = "fast-ariam-v1|<contexto>" (ex.: "tecnico.cpf"): um valor cifrado copiado para OUTRA coluna não decifra.
  * O prefixo "enc1:" identifica formato/versão da chave (permite rotação futura: "enc2:") e torna a migração idempotente.
  * Chaves vêm de app.core.config (obrigatórias, 32 bytes, distintas por finalidade). Nunca em código nem em logs.
"""
import base64
import hashlib
import hmac
import os
from typing import Optional

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.types import Text, TypeDecorator

from app.core import config

PREFIXO = "enc1:"
_AAD_BASE = "fast-ariam-v1"
_TAM_NONCE = 12


class ErroDecifragem(ValueError):
    """Valor cifrado adulterado, de outra coluna, de outra chave — ou texto puro onde só se aceita cifrado."""


def _aad(contexto: str) -> bytes:
    return f"{_AAD_BASE}|{contexto}".encode("utf-8")


def esta_cifrado(valor: Optional[str]) -> bool:
    return isinstance(valor, str) and valor.startswith(PREFIXO)


def cifrar_bytes(dados: bytes, contexto: str) -> bytes:
    """nonce(12) || ciphertext || tag(16), em bytes puros (para arquivos)."""
    nonce = os.urandom(_TAM_NONCE)
    return nonce + AESGCM(config.DATA_ENCRYPTION_KEY).encrypt(nonce, dados, _aad(contexto))


def decifrar_bytes(bruto: bytes, contexto: str) -> bytes:
    if len(bruto) < _TAM_NONCE + 16:
        raise ErroDecifragem("Conteúdo cifrado curto demais.")
    try:
        return AESGCM(config.DATA_ENCRYPTION_KEY).decrypt(bruto[:_TAM_NONCE], bruto[_TAM_NONCE:], _aad(contexto))
    except InvalidTag:
        raise ErroDecifragem("Falha de autenticação: conteúdo adulterado, de outro contexto ou chave incorreta.")


def cifrar(texto: str, contexto: str) -> str:
    return PREFIXO + base64.b64encode(cifrar_bytes(texto.encode("utf-8"), contexto)).decode("ascii")


def decifrar(valor: str, contexto: str) -> str:
    if not esta_cifrado(valor):
        raise ErroDecifragem("Valor sem o prefixo de cifragem.")
    try:
        bruto = base64.b64decode(valor[len(PREFIXO):], validate=True)
    except ValueError:
        raise ErroDecifragem("Base64 inválido no valor cifrado.")
    return decifrar_bytes(bruto, contexto).decode("utf-8")


def indice_cego(valor: Optional[str], contexto: str) -> Optional[str]:
    """
    HMAC-SHA256(INDEX_KEY, contexto|valor) em hex. Determinístico: mesmo valor => mesmo índice (permite WHERE e
    UNIQUE). Sem a INDEX_KEY não é possível recalcular nem testar candidatos (CNPJ tem pouca entropia).
    O chamador deve normalizar o valor antes (ex.: só dígitos).
    """
    if valor is None:
        return None
    msg = f"{contexto}|{valor}".encode("utf-8")
    return hmac.new(config.INDEX_KEY, msg, hashlib.sha256).hexdigest()


class TextoCifrado(TypeDecorator):
    """Coluna de texto cifrada de forma transparente. `contexto` (tabela.coluna) entra como AAD."""
    impl = Text
    cache_ok = True

    def __init__(self, contexto: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.contexto = contexto

    def process_bind_param(self, valor, dialect):
        if valor is None:
            return None
        return cifrar(str(valor), self.contexto)  # sempre cifra: nunca confiar que um valor "já veio cifrado"

    def process_result_value(self, valor, dialect):
        if valor is None:
            return None
        if esta_cifrado(valor):
            return decifrar(valor, self.contexto)
        if config.ENCRYPTION_ALLOW_LEGACY_PLAINTEXT:
            return valor  # linha antiga ainda não migrada (será cifrada por scripts/cifrar_dados_existentes.py)
        raise ErroDecifragem(f"Valor em claro em coluna cifrada ({self.contexto}): possível adulteração.")
