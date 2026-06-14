import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.db.database import engine, Base
from app.models import tecnico, cliente, chamado, visita, servico_equipamento, material, comprovante, servico_defeito, servico_foto, pausa

Base.metadata.create_all(bind=engine)

# TODO: Lembrar de documentar melhor as classes, métodos e utilizar as docstrings para melhorar as descrições no Swagger
# TODO: Durante a refatoração, documentação e validações, lembrar de alterar algumas ordens dos atributos dos retornos dos Endpoints

app = FastAPI(
    title="Fast Ariam API",
    description="API para o sistema de gerenciamento de Ordens de Serviço da Fast Ariam.",
    version="0.1.0" # Protótipo humildão
)


origins = [
    "http://localhost",
    "http://localhost:3000",
    # TODO: Adicionar a URL de produção
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router, prefix="/api")

@app.get("/", tags=["Root"])
def read_root():
    return {"status": "A API da Fast Ariam está no ar!"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)