"""Liga o motor de correlação (puro) ao banco: busca eventos, grava alertas novos.

Chamado logo depois de gravar um evento. Só grava alertas que incluem o
evento novo: tudo o que não depende dele já foi avaliado quando os outros
eventos chegaram.
"""

import hashlib
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.banco import Alerta, Evento
from app.correlacao import RAJADA_JANELA, AlertaProposto, correlacionar


def assinatura(eventos_ids: tuple[int, ...]) -> str:
    """Hash do conjunto de eventos (ordem não importa), usado contra duplicatas."""
    texto = ",".join(str(i) for i in sorted(set(eventos_ids)))
    return hashlib.sha256(texto.encode()).hexdigest()


def _eventos_proximos(sessao: Session, evento: Evento, janela: timedelta) -> list[Evento]:
    """Eventos do mesmo alvo que podem formar um alerta junto com `evento`.

    O motor olha para trás a partir de cada evento. Um alerta que contém o
    evento novo tem sua âncora em [novo, novo + alcance] e olha até
    [âncora - alcance], então basta buscar [novo - alcance, novo + alcance].
    """
    alcance = max(janela, RAJADA_JANELA)
    consulta = select(Evento).where(
        Evento.alvo == evento.alvo,
        Evento.ocorrido_em >= evento.ocorrido_em - alcance,
        Evento.ocorrido_em <= evento.ocorrido_em + alcance,
    )
    return list(sessao.scalars(consulta))


def _novo_alerta(proposto: AlertaProposto) -> Alerta:
    return Alerta(
        regra=proposto.regra,
        nivel=proposto.nivel.value,
        alvo=proposto.alvo,
        resumo=proposto.resumo,
        eventos_ids=list(proposto.eventos_ids),
        assinatura=assinatura(proposto.eventos_ids),
    )


def gravar_alertas_do_evento(sessao: Session, evento: Evento, janela: timedelta) -> list[Alerta]:
    """Correlaciona o evento (já gravado) e grava os alertas que ainda não existem."""
    propostos = [
        p for p in correlacionar(_eventos_proximos(sessao, evento, janela), janela)
        if evento.id in p.eventos_ids
    ]
    if not propostos:
        return []

    existentes = {
        (regra, assin)
        for regra, assin in sessao.execute(
            select(Alerta.regra, Alerta.assinatura).where(Alerta.alvo == evento.alvo)
        )
    }
    novos = [
        _novo_alerta(p) for p in propostos
        if (p.regra, assinatura(p.eventos_ids)) not in existentes
    ]
    if not novos:
        return []

    sessao.add_all(novos)
    try:
        sessao.commit()
        return novos
    except IntegrityError:
        # Outra requisição gravou algum destes ao mesmo tempo: tenta um por um,
        # ignorando os que já existem (a restrição única do banco decide).
        sessao.rollback()

    gravados = []
    for alerta in novos:
        copia = Alerta(
            regra=alerta.regra, nivel=alerta.nivel, alvo=alerta.alvo, resumo=alerta.resumo,
            eventos_ids=alerta.eventos_ids, assinatura=alerta.assinatura,
        )
        sessao.add(copia)
        try:
            sessao.commit()
            gravados.append(copia)
        except IntegrityError:
            sessao.rollback()
    return gravados
