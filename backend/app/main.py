import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.db.database import engine, Base
from app.core.config import CORS_ORIGINS, AUTO_CREATE_TABLES
from app.models import tecnico, cliente, chamado, visita, servico_equipamento, material, comprovante, servico_defeito, servico_foto, pausa, configuracao_custo, custo_os, sync_evento, log_acao, equipamento_modelo, os_equipamento, sync_arquivo

# create_all só roda quando AUTO_CREATE_TABLES=true (apenas dev/test; recusado com ENV=production). O schema de
# produção evolui por migração versionada e nunca deve ser criado/alterado automaticamente no startup (PR-19).
if AUTO_CREATE_TABLES:
    Base.metadata.create_all(bind=engine)

# TODO: Lembrar de documentar melhor as classes, métodos e utilizar as docstrings para melhorar as descrições no Swagger
# TODO: Durante a refatoração, documentação e validações, lembrar de alterar algumas ordens dos atributos dos retornos dos Endpoints

app = FastAPI(
    title="Fast Ariam API",
    description="API para o sistema de gerenciamento de Ordens de Serviço da Fast Ariam.",
    version="0.1.0" # Protótipo humildão
)


# Origens vêm de CORS_ORIGINS (SEG-03). Com allow_credentials=True nunca usar "*" (recusado em app.core.config).
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)



@app.middleware("http")
async def nosniff_em_static(request, call_next):
    """Arquivos enviados por usuários em /static nunca devem ser reinterpretados pelo navegador (Segurança M4)."""
    resposta = await call_next(request)
    if request.url.path.startswith("/static"):
        resposta.headers["X-Content-Type-Options"] = "nosniff"
    return resposta


app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router, prefix="/api")

@app.get("/", tags=["Root"])
def read_root():
    return {"status": "A API da Fast Ariam está no ar!"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)