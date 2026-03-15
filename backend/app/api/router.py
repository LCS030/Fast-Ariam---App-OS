from fastapi import APIRouter
from app.api.endpoints import chamados, tecnicos, clientes, auth

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Auth"])
api_router.include_router(chamados.router, prefix="/chamados", tags=["Chamados"])
api_router.include_router(tecnicos.router, prefix="/tecnicos", tags=["Técnicos"])
api_router.include_router(clientes.router, prefix="/clientes", tags=["Clientes"])
