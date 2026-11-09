import logging
import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Variável de ambiente DATABASE_URL não definida, crie uma DATABASE_URL no arquivo .env")


def _connect_args(url: str) -> dict:
    """
    TLS obrigatório até o banco (Confidencialidade em trânsito). No PostgreSQL o padrão do libpq é `prefer`, que aceita
    conexão SEM TLS; aqui o mínimo é `require` (criptografa, mas NÃO valida o certificado). Para validar a identidade do
    servidor (recomendado em produção) use DB_SSLMODE=verify-full e DB_SSLROOTCERT=<ca.crt do Supabase>.
    Modos sem TLS (disable/allow/prefer) só são aceitos fora de produção, para um PostgreSQL local de desenvolvimento.
    SQLite (testes) não usa TLS: nenhum argumento.
    """
    if make_url(url).get_backend_name() != "postgresql":
        return {}
    from app.core.config import IS_PRODUCTION  # import tardio: config valida as chaves e não depende do banco

    modo = (os.getenv("DB_SSLMODE") or "require").strip().lower()
    if modo not in ("require", "verify-ca", "verify-full"):
        if modo in ("disable", "allow", "prefer") and not IS_PRODUCTION:
            logging.getLogger(__name__).warning("DB_SSLMODE=%s: conexão com o banco SEM TLS obrigatório (só em dev).", modo)
        else:
            raise ValueError("DB_SSLMODE inválido. Use require, verify-ca ou verify-full (TLS é obrigatório em produção).")
    if modo == "require" and IS_PRODUCTION:
        logging.getLogger(__name__).warning(
            "DB_SSLMODE=require: a conexão com o banco é cifrada, mas o CERTIFICADO DO SERVIDOR NÃO É VALIDADO "
            "(vulnerável a man-in-the-middle). Em produção use DB_SSLMODE=verify-full com DB_SSLROOTCERT.")
    args = {"sslmode": modo}
    raiz = (os.getenv("DB_SSLROOTCERT") or "").strip()
    if raiz:
        args["sslrootcert"] = raiz
    return args


engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """
    Dependência do FastAPI para gerenciar a sessão do banco de dados e garantir que a sessão sempre feche depois de cada requisição
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
