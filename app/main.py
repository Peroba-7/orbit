from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.banco import criar_tabelas
from app.rotas import eventos


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    # Etapa 1: cria as tabelas na subida. Na etapa de produção, trocar por
    # migrações (Alembic) para evoluir o banco sem perder dados.
    criar_tabelas()
    yield


app = FastAPI(
    title="ORBIT",
    version="0.1.0",
    description=(
        "Mini-SOC: recebe eventos de várias fontes de segurança, guarda num "
        "formato único e (nas próximas etapas) correlaciona e mostra o risco."
    ),
    lifespan=ciclo_de_vida,
)

app.include_router(eventos.router)


@app.get("/saude", tags=["infra"])
def saude() -> dict[str, str]:
    return {"status": "ok"}
