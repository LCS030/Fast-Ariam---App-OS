"""
Armazenamento e validação de imagens (SDD 6.8, seção 7, SEG-08).

ATENÇÃO (PR-03 pendente): os arquivos ainda são gravados em disco local (`static/...`). A migração para o bucket
privado `fast-ariam-privado` do Supabase Storage (URLs assinadas, SEG-09) NÃO faz parte desta rodada. Toda gravação
passa por `save_*` deste módulo para que a troca do destino fique concentrada aqui.

Regras aplicadas ANTES de persistir qualquer byte:
  * tamanho <= 15 MB            -> 413
  * formato real JPEG/PNG       -> 422 (verificado com Pillow, não pelo Content-Type nem pela extensão)
  * resolução mínima 960x1280   -> 400, SOMENTE para foto de conserto (RN-21 / PR-29)
"""
import base64
import binascii
import logging
import os
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

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


@dataclass
class ImagemValidada:
    data: bytes
    formato: str  # "JPEG" | "PNG"
    extensao: str  # ".jpg" | ".png"
    largura: int
    altura: int


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
                          largura=largura, altura=altura)


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


def validar_imagem_upload(file: UploadFile, *, exigir_resolucao_minima: bool = False) -> ImagemValidada:
    """Lê e valida o upload. Só retorna se estiver tudo certo; nada é gravado em disco aqui."""
    imagem = _analisar_imagem(_ler_upload(file))
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


def salvar_imagem(imagem: ImagemValidada, prefix: str) -> str:
    """Grava uma imagem já validada e devolve a URL relativa (`/static/uploads/...`)."""
    nome = f"{prefix}_{uuid.uuid4().hex[:8]}{imagem.extensao}"
    _gravar(UPLOAD_DIRECTORY, nome, imagem.data)
    return f"{UPLOAD_URL_PREFIX}/{nome}"


def save_upload_file(file: UploadFile, prefix: str, *, exigir_resolucao_minima: bool = False) -> str:
    """Valida (tamanho, formato real, resolução se pedido) e grava o upload. Retorna a URL relativa."""
    return salvar_imagem(validar_imagem_upload(file, exigir_resolucao_minima=exigir_resolucao_minima), prefix)


def decodificar_assinatura(assinatura_base64: str) -> ImagemValidada:
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
    try:
        return _analisar_imagem(dados)
    except HTTPException as exc:
        if exc.status_code == 422:
            raise HTTPException(status_code=400, detail="Assinatura inválida: envie uma imagem PNG ou JPEG.")
        raise


def salvar_assinatura(imagem: ImagemValidada) -> str:
    """Grava a assinatura e devolve a URL relativa (`/static/assinaturas/...`)."""
    nome = f"{uuid.uuid4().hex}{imagem.extensao}"
    _gravar(ASSINATURA_DIRECTORY, nome, imagem.data)
    return f"{ASSINATURA_URL_PREFIX}/{nome}"


def remover_arquivo_por_url(url: Optional[str]) -> None:
    """Remove um arquivo gravado por este módulo (compensação quando a transação falha). Melhor esforço."""
    if not url:
        return
    try:
        if url.startswith(ASSINATURA_URL_PREFIX + "/"):
            (ASSINATURA_DIRECTORY / url.rsplit("/", 1)[1]).unlink(missing_ok=True)
        elif url.startswith(UPLOAD_URL_PREFIX + "/"):
            (UPLOAD_DIRECTORY / url.rsplit("/", 1)[1]).unlink(missing_ok=True)
    except OSError:  # pragma: no cover
        logger.warning("Falha ao remover arquivo órfão %s", url)
