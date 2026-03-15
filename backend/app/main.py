# app/main.py
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.routing import APIRoute
from fastapi import FastAPI
from app.api.router import api_router

class NoSlashRedirectFastAPI(FastAPI):
    def setup(self):
        super().setup()
        for route in self.routes:
            if isinstance(route, APIRoute):
                route.redirect_slashes = False

app = NoSlashRedirectFastAPI(
    title="Fast Ariam API",
    description="API para o sistema de gerenciamento de Ordens de Serviço da Fast Ariam.",
    version="0.1.0"
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router, prefix="/api")

@app.get("/", tags=["Root"])
def read_root():
    return {"status": "A API da Fast Ariam está no ar!"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

