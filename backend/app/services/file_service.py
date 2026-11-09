"""
Armazenamento e validação de imagens (SDD 6.8, seção 7, SEG-08).

ARMAZENAMENTO (PR-03 / SEG-09): toda gravação, leitura e remoção passa por `armazenamento()`, que devolve o bucket PRIVADO
do Supabase Storage (`storage_service.SupabaseStorage`) quando SUPABASE_URL e SUPABASE_SERVICE_KEY existem, ou o disco
local (`ArmazenamentoLocal`, somente dev/teste; recusado em ENV=production). A `url` guardada no banco é uma referência
LÓGICA (`/static/uploads/<nome>`, `/static/assinaturas/<nome>.enc`) que NÃO é servida: os arquivos só saem por rotas
autenticadas da API. Manter a referência estável preserva os selos de integridade já gravados.

Regras aplicadas ANTES de persistir qualquer byte:
  * tamanho <= 15 MB            -> 413
  * formato real JPEG/PNG       -> 422 (verificado com Pillow, não pelo Content-Type nem pela extensão)
  * resolução mínima 960x1280   -> 400, SOMENTE para foto de conserto (RN-21 / PR-29)
"""
import base64
import binascii
import hashlib
import hmac
import logging
import os
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from app.core import config
from app.core.crypto import cifrar_bytes, decifrar_bytes
from app.core.erros import ErroRegra
from app.services.storage_service import SupabaseStorage

logger = logging.getLogger(__name__)

# Diretórios configuráveis por ambiente (os testes apontam para uma pasta temporária).
UPLOAD_DIRECTORY = Path(os.getenv("UPLOAD_DIR", "static/uploads"))
ASSINATURA_DIRECTORY = Path(os.getenv("ASSINATURA_DIR", "static/assinaturas"))
# Prefixos públicos servidos pelo mount /static (mantidos até a migração para o Storage).
UPLOAD_URL_PREFIX = "/static/uploads"
ASSINATURA_URL_PREFIX = "/static/assinaturas"

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB por arquivo (SDD 6.8)
MIN_RESOLUTION_WIDTH = 960
MIN_RESOLUTION_HEIGHT = 1280
_FORMATOS_PERMITIDOS = {"JPEG": ".jpg", "PNG": ".png"}
_CHUNK = 1024 * 1024


# Contexto (AAD) do AES-GCM da assinatura em disco: um arquivo .enc copiado para outro contexto não decifra.
CONTEXTO_ASSINATURA = "arquivo.assinatura"
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


@dataclass
class ImagemValidada:
    data: bytes
    formato: str  # "JPEG" | "PNG"
    extensao: str  # ".jpg" | ".png"
    largura: int
    altura: int
    sha256: str = ""  # SHA-256 dos bytes recebidos (calculado SEMPRE pelo servidor)


@dataclass
class ArquivoSalvo:
    url: str
    sha256: str


# --- Integridade: SHA-256 dos arquivos -----------------------------------------------------------------------------
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def conferir_hash(data: bytes, informado: Optional[str]) -> str:
    """
    Recalcula o SHA-256 dos bytes recebidos e compara (tempo constante) com o hash calculado no aparelho. Divergência
    => 422 HASH_DIVERGENTE: o arquivo que chegou NÃO é o que saiu do celular (corrompido em trânsito ou alterado na fila).
    Sem hash informado, só é aceito se a origem não for obrigatória (config.SHA256_ORIGEM_OBRIGATORIO); o servidor
    grava o hash que ele mesmo calculou de qualquer forma. Retorna o hash calculado.
    """
    calculado = sha256_hex(data)
    if informado is None or not str(informado).strip():
        if config.SHA256_ORIGEM_OBRIGATORIO:
            raise ErroRegra(422, "Informe o SHA-256 do arquivo (campo 'sha256').", "HASH_AUSENTE")
        return calculado
    informado = str(informado).strip().lower()
    if not _SHA256_HEX.match(informado):
        raise ErroRegra(422, "SHA-256 inválido: envie 64 caracteres hexadecimais.", "HASH_INVALIDO")
    if not hmac.compare_digest(calculado, informado):
        raise ErroRegra(422, "Arquivo corrompido em trânsito (hash divergente).", "HASH_DIVERGENTE")
    return calculado


def _mensagem_limite() -> str:
    return f"Imagem acima do limite de {MAX_IMAGE_BYTES // (1024 * 1024)} MB."


def _ler_upload(file: UploadFile) -> bytes:
    """Lê o upload em blocos e aborta (413) assim que passa do limite, sem carregar arquivos gigantes."""
    buffer = bytearray()
    try:
        file.file.seek(0)
        while True:
            bloco = file.file.read(_CHUNK)
            if not bloco:
                break
            buffer.extend(bloco)
            if len(buffer) > MAX_IMAGE_BYTES:
                raise HTTPException(status_code=413, detail=_mensagem_limite())
    finally:
        try:
            file.file.close()
        except Exception:  # pragma: no cover - fechamento é melhor esforço
            pass
    if not buffer:
        raise HTTPException(status_code=422, detail="Arquivo de imagem vazio.")
    return bytes(buffer)


def _analisar_imagem(data: bytes) -> ImagemValidada:
    """Valida o conteúdo real com Pillow: tem de ser uma imagem íntegra JPEG ou PNG."""
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail=_mensagem_limite())
    try:
        with Image.open(BytesIO(data)) as img:
            formato = (img.format or "").upper()
            largura, altura = img.size
            img.verify()  # detecta arquivo truncado/corrompido sem decodificar tudo
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise HTTPException(status_code=422, detail="Arquivo inválido: envie uma imagem JPEG ou PNG.")
    if formato not in _FORMATOS_PERMITIDOS:
        raise HTTPException(status_code=422, detail="Formato não permitido: envie uma imagem JPEG ou PNG.")
    return ImagemValidada(data=data, formato=formato, extensao=_FORMATOS_PERMITIDOS[formato],
                          largura=largura, altura=altura, sha256=sha256_hex(data))


def _exigir_resolucao_minima(imagem: ImagemValidada) -> None:
    """
    960x1280 independente da orientação: o app pode capturar em retrato ou paisagem (a câmera grava a mesma
    quantidade de pixels). Interpretação registrada no relatório para confirmação do PO.
    """
    menor, maior = sorted((imagem.largura, imagem.altura))
    if menor < MIN_RESOLUTION_WIDTH or maior < MIN_RESOLUTION_HEIGHT:
        raise HTTPException(
            status_code=400,
            detail=(f"Resolução insuficiente. Mínimo requerido: {MIN_RESOLUTION_WIDTH}x{MIN_RESOLUTION_HEIGHT}. "
                    f"Resolução da imagem: {imagem.largura}x{imagem.altura}."))


def validar_imagem_upload(file: UploadFile, *, exigir_resolucao_minima: bool = False,
                          sha256_informado: Optional[str] = None) -> ImagemValidada:
    """Lê e valida o upload. Só retorna se estiver tudo certo; nada é gravado em disco aqui."""
    bruto = _ler_upload(file)
    conferir_hash(bruto, sha256_informado)  # 422 antes de qualquer outra análise
    imagem = _analisar_imagem(bruto)
    if exigir_resolucao_minima:
        _exigir_resolucao_minima(imagem)
    return imagem


def _gravar(diretorio: Path, nome: str, conteudo: bytes) -> Path:
    diretorio.mkdir(parents=True, exist_ok=True)
    caminho = diretorio / nome
    # Grava em arquivo temporário e renomeia: nunca deixa arquivo parcial no destino final.
    temporario = caminho.with_name(caminho.name + ".part")
    try:
        temporario.write_bytes(conteudo)
        temporario.replace(caminho)
    finally:
        if temporario.exists():
            temporario.unlink(missing_ok=True)
    return caminho


class ArmazenamentoLocal:
    """Disco local (dev/teste). Lê os diretórios do módulo a cada chamada (os testes os trocam por pastas temporárias)."""

    @staticmethod
    def _dir(area: str) -> Path:
        return ASSINATURA_DIRECTORY if area == "assinaturas" else UPLOAD_DIRECTORY

    def put(self, area: str, nome: str, dados: bytes, content_type: str) -> None:
        _gravar(self._dir(area), nome, dados)

    def get(self, area: str, nome: str) -> Optional[bytes]:
        caminho = self._dir(area) / nome
        return caminho.read_bytes() if caminho.is_file() else None

    def delete(self, area: str, nome: str) -> None:
        (self._dir(area) / nome).unlink(missing_ok=True)


_ARMAZENAMENTO = None  # instância única (cache); os testes podem substituí-la


def armazenamento():
    """Backend de armazenamento escolhido pela configuração: Supabase Storage privado ou disco local."""
    global _ARMAZENAMENTO
    if _ARMAZENAMENTO is None:
        if config.STORAGE_BACKEND == "supabase":
            _ARMAZENAMENTO = SupabaseStorage(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, config.STORAGE_BUCKET)
        else:
            _ARMAZENAMENTO = ArmazenamentoLocal()
    return _ARMAZENAMENTO


def _referencia(url: Optional[str]):
    """(area, nome) de uma referência lógica gravada por este módulo, ou None se for inválida (anti path traversal)."""
    if not url:
        return None
    for area, prefixo in (("assinaturas", ASSINATURA_URL_PREFIX), ("uploads", UPLOAD_URL_PREFIX)):
        if url.startswith(prefixo + "/"):
            nome = url[len(prefixo) + 1:]
            # exatamente <prefixo>/<nome>, sem subpastas, "..", barras ou invertidas
            if nome and nome not in (".", "..") and "/" not in nome and "\\" not in nome and Path(nome).name == nome:
                return area, nome
            return None
    return None


def salvar_imagem(imagem: ImagemValidada, prefix: str) -> str:
    """Grava uma imagem já validada e devolve a referência (`/static/uploads/...`)."""
    nome = f"{prefix}_{uuid.uuid4().hex[:8]}{imagem.extensao}"
    armazenamento().put("uploads", nome, imagem.data, "image/png" if imagem.formato == "PNG" else "image/jpeg")
    return f"{UPLOAD_URL_PREFIX}/{nome}"


def salvar_upload(file: UploadFile, prefix: str, *, exigir_resolucao_minima: bool = False,
                  sha256_informado: Optional[str] = None) -> ArquivoSalvo:
    """Valida (hash, tamanho, formato real, resolução se pedido), grava e devolve URL + SHA-256 do arquivo."""
    imagem = validar_imagem_upload(file, exigir_resolucao_minima=exigir_resolucao_minima,
                                   sha256_informado=sha256_informado)
    return ArquivoSalvo(url=salvar_imagem(imagem, prefix), sha256=imagem.sha256)


def save_upload_file(file: UploadFile, prefix: str, *, exigir_resolucao_minima: bool = False,
                     sha256_informado: Optional[str] = None) -> str:
    """Como `salvar_upload`, mas devolve só a URL relativa (compatibilidade)."""
    return salvar_upload(file, prefix, exigir_resolucao_minima=exigir_resolucao_minima,
                         sha256_informado=sha256_informado).url


def decodificar_assinatura(assinatura_base64: str, sha256_informado: Optional[str] = None) -> ImagemValidada:
    """
    Decodifica a assinatura (PNG/JPEG em base64, com ou sem prefixo `data:image/...;base64,`).
    Base64 inválido ou conteúdo que não é imagem -> 400 (nunca 500). Mais de 15 MB -> 413.
    """
    texto = (assinatura_base64 or "").strip()
    if texto.startswith("data:"):
        _, _, texto = texto.partition(",")
    # Limite aproximado antes de decodificar (base64 ocupa ~4/3 do binário).
    if len(texto) > (MAX_IMAGE_BYTES * 4) // 3 + 8:
        raise HTTPException(status_code=413, detail=_mensagem_limite())
    try:
        dados = base64.b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="Assinatura inválida: base64 malformado.")
    if not dados:
        raise HTTPException(status_code=400, detail="Assinatura inválida: conteúdo vazio.")
    conferir_hash(dados, sha256_informado)
    try:
        return _analisar_imagem(dados)
    except HTTPException as exc:
        if exc.status_code == 422:
            raise HTTPException(status_code=400, detail="Assinatura inválida: envie uma imagem PNG ou JPEG.")
        raise


def salvar_assinatura(imagem: ImagemValidada) -> str:
    """
    Grava a assinatura CIFRADA (AES-256-GCM, `.enc`) e devolve a referência (`/static/assinaturas/<uuid>.enc`). Essa
    referência é só um identificador: /static/assinaturas NÃO é servido; a imagem sai pelo endpoint autenticado
    `GET /api/chamados/{id}/visitas/{v}/assinatura`. O hash (imagem.sha256) é dos bytes ANTES de cifrar.
    """
    nome = f"{uuid.uuid4().hex}.enc"
    armazenamento().put("assinaturas", nome, cifrar_bytes(imagem.data, CONTEXTO_ASSINATURA), "application/octet-stream")
    return f"{ASSINATURA_URL_PREFIX}/{nome}"


def ler_arquivo_por_url(url: Optional[str]) -> Optional[bytes]:
    """
    Lê os bytes originais de um arquivo gravado por este módulo (assinatura `.enc` é decifrada; assinaturas antigas em
    claro e fotos são lidas como estão). None se não existir ou se a referência for inválida. Lança ErroDecifragem se um
    `.enc` foi adulterado e HTTPException 503 se o Storage estiver indisponível.
    """
    ref = _referencia(url)
    if ref is None:
        return None
    area, nome = ref
    bruto = armazenamento().get(area, nome)
    if bruto is None:
        return None
    return decifrar_bytes(bruto, CONTEXTO_ASSINATURA) if nome.endswith(".enc") else bruto


def tipo_mime_da_imagem(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def remover_arquivo_por_url(url: Optional[str]) -> None:
    """Remove um arquivo gravado por este módulo (compensação quando a transação falha). Melhor esforço."""
    ref = _referencia(url)
    if ref is None:
        return
    try:
        armazenamento().delete(*ref)
    except Exception:  # pragma: no cover - compensação é melhor esforço
        logger.warning("Falha ao remover arquivo órfão %s", url)
