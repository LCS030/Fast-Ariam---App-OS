from fastapi import APIRouter
from app.api.endpoints import chamados, tecnicos, clientes, auth, equipamentos, sync

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(chamados.router, prefix="/chamados", tags=["Chamados"])
api_router.include_router(tecnicos.router, prefix="/tecnicos", tags=["Técnicos"])
api_router.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
api_router.include_router(equipamentos.router, prefix="/equipamentos", tags=["Equipamentos"])
api_router.include_router(sync.router, prefix="/sync", tags=["Sincronização offline"])
