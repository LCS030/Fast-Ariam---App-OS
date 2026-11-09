"""
Configuração central do backend (SDD seção 2 e 6.11).

Tudo que varia por ambiente vem de variáveis de ambiente / .env. Nenhum segredo é hardcoded.
"""
import logging
import os
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

# --- Ambiente ---------------------------------------------------------------------------------------------------------
# ENV: "development" (padrão), "test" ou "production". Usado como guarda por scripts destrutivos e por CORS.
ENV = os.getenv("ENV", "development").strip().lower()
IS_PRODUCTION = ENV in ("production", "prod")

# --- JWT (SDD 6.2 / SEG-07) -------------------------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))

if not SECRET_KEY:
    raise ValueError("SECRET_KEY não definida no .env. Crie um arquivo .env e crie uma SECRET_KEY.")

# Segurança A2: HS256 com chave curta é quebrável por força bruta. Produção exige >= 32 caracteres; em dev apenas avisa.
SECRET_KEY_MIN_LENGTH = 32
if len(SECRET_KEY) < SECRET_KEY_MIN_LENGTH:
    if IS_PRODUCTION:
        raise ValueError(f"SECRET_KEY deve ter pelo menos {SECRET_KEY_MIN_LENGTH} caracteres quando ENV=production.")
    logging.getLogger(__name__).warning(
        "SECRET_KEY tem menos de %d caracteres; use uma chave longa e aleatória (obrigatório em produção).",
        SECRET_KEY_MIN_LENGTH)

# O algoritmo nunca pode vir "livre": somente HMAC simétrico (a SDD v0.3 documenta HS256). Impede "none" por configuração.
if ALGORITHM not in ("HS256", "HS384", "HS512"):
    raise ValueError("ALGORITHM inválido. Use HS256 (padrão), HS384 ou HS512.")


# --- CORS (SEG-03 / PR-18) --------------------------------------------------------------------------------------------
# Origens usadas apenas em desenvolvimento quando CORS_ORIGINS não é informada (painel Vite e CRA/Next local).
DEFAULT_DEV_CORS_ORIGINS: List[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]


def parse_cors_origins(raw: Optional[str], production: bool = False) -> List[str]:
    """
    Converte CORS_ORIGINS (lista separada por vírgula) em lista de origens.

    - Sem valor: usa os padrões de desenvolvimento; em produção a variável é obrigatória.
    - "*" é recusado: o middleware usa allow_credentials=True e navegadores rejeitam "*" com credenciais.
    """
    origins = [o.strip().rstrip("/") for o in (raw or "").split(",") if o.strip()]
    if not origins:
        if production:
            raise ValueError("CORS_ORIGINS é obrigatória quando ENV=production (lista separada por vírgula).")
        return list(DEFAULT_DEV_CORS_ORIGINS)
    if "*" in origins:
        raise ValueError("CORS_ORIGINS não pode conter '*' (a API usa allow_credentials=True). Liste as origens.")
    return origins


CORS_ORIGINS: List[str] = parse_cors_origins(os.getenv("CORS_ORIGINS"), production=IS_PRODUCTION)


# --- Criação automática de tabelas (PR-19) ----------------------------------------------------------------------------
def auto_create_tables_enabled(raw: Optional[str], production: bool) -> bool:
    """
    AUTO_CREATE_TABLES=true liga Base.metadata.create_all no startup. Só para dev/test: o schema de produção
    evolui por migração versionada (DBA), nunca por create_all. Em produção a variável é recusada.
    """
    ligado = (raw or "").strip().lower() in ("1", "true", "yes", "sim", "on")
    if ligado and production:
        raise ValueError("AUTO_CREATE_TABLES não pode ser habilitada com ENV=production. Use migrações.")
    return ligado


AUTO_CREATE_TABLES: bool = auto_create_tables_enabled(os.getenv("AUTO_CREATE_TABLES"), IS_PRODUCTION)


# --- Valores globais de referência de custo (SDD 6.11 / PR-22 / PR-33 / RN-32) -----------------------------------------
# Valores GLOBAIS do sistema: não são por técnico e o técnico não os altera. Não existe endpoint de configuração por
# técnico. Ajudantes estão fora do escopo v0.3 (chaves de ajudante removidas). O snapshot em custo_os é do Backend A.
# Pendência: a tabela configuracao_custo (DBA) deve passar a ser a fonte; estes valores são o fallback atual.
VALORES_ASSISTENCIA = {
    "PRIMEIRA_HORA_TECNICO": 87.01,
    "HORA_TECNICO": 62.15,
    "TEMPO_DESLOCAMENTO_TECNICO": 24.86,
    "QUILOMETRAGEM": 1.15,
}
