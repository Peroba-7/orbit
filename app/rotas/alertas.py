from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.banco import Alerta, Evento, obter_sessao
from app.esquemas import (
    AlertaDetalhado,
    AlertaSaida,
    EventoSaida,
    Nivel,
    niveis_a_partir_de,
    normalizar_alvo,
)
from app.seguranca import exigir_chave

router = APIRouter(prefix="/alertas", tags=["alertas"], dependencies=[Depends(exigir_chave)])

SessaoDep = Annotated[Session, Depends(obter_sessao)]


@router.get("", response_model=list[AlertaSaida])
def listar_alertas(
    sessao: SessaoDep,
    alvo: Annotated[str | None, Query(max_length=255)] = None,
    nivel_minimo: Nivel | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[Alerta]:
    """Lista alertas, do mais recente para o mais antigo."""
    consulta = select(Alerta).order_by(Alerta.criado_em.desc(), Alerta.id.desc())
    if alvo is not None:
        consulta = consulta.where(Alerta.alvo == normalizar_alvo(alvo))
    if nivel_minimo is not None:
        niveis = [n.value for n in niveis_a_partir_de(nivel_minimo)]
        consulta = consulta.where(Alerta.nivel.in_(niveis))
    return list(sessao.scalars(consulta.limit(limite)))


@router.get("/{alerta_id}", response_model=AlertaDetalhado)
def obter_alerta(alerta_id: int, sessao: SessaoDep) -> AlertaDetalhado:
    """Um alerta com os eventos que o causaram, em ordem cronológica."""
    alerta = sessao.get(Alerta, alerta_id)
    if alerta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alerta não encontrado.")
    eventos = sessao.scalars(
        select(Evento)
        .where(Evento.id.in_(alerta.eventos_ids))
        .order_by(Evento.ocorrido_em, Evento.id)
    )
    return AlertaDetalhado(
        **AlertaSaida.model_validate(alerta).model_dump(),
        eventos=[EventoSaida.model_validate(e) for e in eventos],
    )
