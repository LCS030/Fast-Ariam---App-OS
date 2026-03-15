import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("Variável de ambiente DATABASE_URL não definida, crie uma DATABASE_URL no arquivo .env")

engine = create_engine(DATABASE_URL)
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
