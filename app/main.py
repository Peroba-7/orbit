from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.banco import criar_tabelas
from app.config import janela_horas
from app.rotas import alertas, eventos


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    # Configuração inválida derruba a subida, em vez de falhar a cada evento.
    janela_horas()
    # Etapa 1: cria as tabelas na subida. Na etapa de produção, trocar por
    # migrações (Alembic) para evoluir o banco sem perder dados.
    criar_tabelas()
    yield


app = FastAPI(
    title="ORBIT",
    version="0.2.0",
    description=(
        "Mini-SOC: recebe eventos de várias fontes de segurança, guarda num "
        "formato único e correlaciona sinais do mesmo alvo em alertas explicáveis."
    ),
    lifespan=ciclo_de_vida,
)

app.include_router(eventos.router)
app.include_router(alertas.router)


@app.get("/saude", tags=["infra"])
def saude() -> dict[str, str]:
    return {"status": "ok"}
