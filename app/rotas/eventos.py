from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alertas import gravar_alertas_do_evento
from app.banco import Evento, obter_sessao
from app.config import janela_horas
from app.esquemas import (
    EventoEntrada,
    EventoSaida,
    Nivel,
    Origem,
    niveis_a_partir_de,
    normalizar_alvo,
)
from app.seguranca import exigir_chave

router = APIRouter(prefix="/eventos", tags=["eventos"], dependencies=[Depends(exigir_chave)])

SessaoDep = Annotated[Session, Depends(obter_sessao)]


@router.post("", response_model=EventoSaida, status_code=status.HTTP_201_CREATED)
def registrar_evento(entrada: EventoEntrada, sessao: SessaoDep) -> Evento:
    """Recebe um evento de uma fonte, guarda no banco e roda a correlação.

    Os alertas gerados aparecem em GET /alertas.
    """
    evento = Evento(
        origem=entrada.origem.value,
        tipo=entrada.tipo,
        alvo=entrada.alvo,
        nivel=entrada.nivel.value,
        resumo=entrada.resumo,
        detalhes=entrada.detalhes,
        ocorrido_em=entrada.ocorrido_em,
    )
    sessao.add(evento)
    sessao.commit()
    gravar_alertas_do_evento(sessao, evento, timedelta(hours=janela_horas()))
    return evento


@router.get("", response_model=list[EventoSaida])
def listar_eventos(
    sessao: SessaoDep,
    origem: Origem | None = None,
    alvo: Annotated[str | None, Query(max_length=255)] = None,
    nivel_minimo: Nivel | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Evento]:
    """Lista eventos, do mais recente para o mais antigo, com filtros simples."""
    consulta = select(Evento).order_by(Evento.ocorrido_em.desc(), Evento.id.desc())
    if origem is not None:
        consulta = consulta.where(Evento.origem == origem.value)
    if alvo is not None:
        consulta = consulta.where(Evento.alvo == normalizar_alvo(alvo))
    if nivel_minimo is not None:
        niveis = [n.value for n in niveis_a_partir_de(nivel_minimo)]
        consulta = consulta.where(Evento.nivel.in_(niveis))
    return list(sessao.scalars(consulta.limit(limite)))


@router.get("/{evento_id}", response_model=EventoSaida)
def obter_evento(evento_id: int, sessao: SessaoDep) -> Evento:
    evento = sessao.get(Evento, evento_id)
    if evento is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evento não encontrado.")
    return evento
