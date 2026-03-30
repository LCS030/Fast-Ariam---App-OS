import shutil
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from PIL import Image
from io import BytesIO

UPLOAD_DIRECTORY = Path("static/uploads")
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)

MIN_RESOLUTION_WIDTH = 960
MIN_RESOLUTION_HEIGHT = 1280


def validate_image_resolution(file: UploadFile) -> None:
    """
    Valida se a imagem possui resolução mínima de 960x1280.
    
    Args:
        file: O arquivo FastAPI UploadFile.
        
    Raises:
        HTTPException: Se a imagem for menor que 960x1280.
    """
    try:
        # Ler a imagem diretamente do arquivo
        file.file.seek(0)
        image = Image.open(file.file)
        width, height = image.size
        
        # Voltar ao início do arquivo para posterior leitura
        file.file.seek(0)
        
        if width < MIN_RESOLUTION_WIDTH or height < MIN_RESOLUTION_HEIGHT:
            raise HTTPException(
                status_code=400, 
                detail=f"Resolução insuficiente. Mínimo requerido: {MIN_RESOLUTION_WIDTH}x{MIN_RESOLUTION_HEIGHT}. Resolução da imagem: {width}x{height}."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao validar imagem: {str(e)}")


def save_upload_file(file: UploadFile, prefix: str) -> str:
    """
    Salva um "UploadFile" e retorna o caminho relativo do arquivo.

    Args:
        file: O arquivo FastAPI UploadFile.
        prefix: Um prefixo para ajudar a identificar o arquivo (ex: 'visita_1_odometro')

    Returns:
        O caminho relativo de onde o arquivo foi salvo.
    """
    try:
        extension = Path(file.filename).suffix
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{prefix}_{unique_id}{extension}"

        file_path = UPLOAD_DIRECTORY / filename

        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

    finally:
        file.file.close()

    # Retornando o caminho RELATIVO da URL
    return f"/{file_path.as_posix()}"
