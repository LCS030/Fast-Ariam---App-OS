import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

if not SECRET_KEY:
    raise ValueError("SECRET_KEY não definida no .env. Crie um arquivo .env e crie uma SECRET_KEY.")

# TODO: Numa possível tela para administradores, seria possível fazer a alteração dos valores brutos sem interromper a aplicação
VALORES_ASSISTENCIA = {
    "PRIMEIRA_HORA_TECNICO": 87.01,
    "HORA_TECNICO": 62.15,
    "HORA_AJUDANTE": 27.57,
    "TEMPO_DESLOCAMENTO_TECNICO": 24.86,
    "TEMPO_DESLOCAMENTO_AJUDANTE": 12.43,
    "QUILOMETRAGEM": 1.15
}

VALORES_MONTAGEM = {
    "MONTAGEM_ILHA": 50.00,
    "MONTAGEM_KIT_PRATELEIRA": 40.00,
    "MONTAGEM_EXPOSITOR": 130.00,
    "MONTAGEM_EXPOSITOR_GEMINADO": 160.00,
    "QUILOMETRAGEM": 1.15
}