import shutil
import uuid
from pathlib import Path
from fastapi import UploadFile

UPLOAD_DIRECTORY = Path("static/uploads")
UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)


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
