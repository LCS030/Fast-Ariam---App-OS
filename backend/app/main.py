import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from app.api.router import api_router
from app.db.database import engine, Base
from app.core import config
from app.core.erros import ErroRegra
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



@app.exception_handler(ErroRegra)
async def erro_regra_com_codigo(request, exc: ErroRegra):
    """Mesma resposta de HTTPException (`detail`) + `codigo` estável (ex.: HASH_DIVERGENTE) para o app decidir se repete."""
    return JSONResponse(status_code=exc.status_code, headers=getattr(exc, "headers", None),
                        content={"detail": exc.detail, "codigo": exc.codigo})


HSTS = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def cabecalhos_de_seguranca(request, call_next):
    """
    * /static: arquivos enviados por usuários nunca devem ser reinterpretados pelo navegador (Segurança M4).
    * Strict-Transport-Security em TODA resposta quando ENV=production: o navegador passa a recusar HTTP para este
      host. Só tem efeito se a API for servida por HTTPS (proxy reverso/uvicorn --ssl-*); em dev fica desligado.
    """
    resposta = await call_next(request)
    if request.url.path.startswith("/static"):
        resposta.headers["X-Content-Type-Options"] = "nosniff"
    if config.IS_PRODUCTION:
        resposta.headers["Strict-Transport-Security"] = HSTS
    return resposta


# Não há mais /static: fotos, comprovantes e assinaturas ficam no armazenamento PRIVADO (bucket do Supabase Storage; disco
# local só em dev/teste) e saem apenas por rotas autenticadas com autorização por OS:
#   GET /api/chamados/{id}/arquivos/conteudo?url=...   e   GET /api/chamados/{id}/visitas/{v}/assinatura
app.include_router(api_router, prefix="/api")

@app.get("/", tags=["Root"])
def read_root():
    return {"status": "A API da Fast Ariam está no ar!"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)