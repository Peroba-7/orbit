"""Liga as regras puras ao banco: busca eventos, grava só os alertas novos.

- Correlação (app/correlacao.py): chamada logo depois de gravar um evento. Só
  grava alertas que incluem o evento novo: tudo o que não depende dele já foi
  avaliado quando os outros eventos chegaram.
- Saúde das fontes (app/saude_fontes.py): chamada de tempos em tempos pelo
  agendador (app/agendador.py), porque uma fonte calada não manda evento.

Nos dois casos o dedupe é o mesmo: (regra, alvo, assinatura), garantido no
fim pela restrição única do banco.
"""

from collections.abc import Iterable
from datetime import datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.banco import Alerta, Evento
from app.correlacao import RAJADA_JANELA, AlertaProposto, assinatura, correlacionar
from app.saude_fontes import CAMPO_VERSAO_REGRAS, TIPO_HEARTBEAT, verificar_saude

__all__ = ["assinatura", "gravar_alertas_do_evento", "verificar_saude_e_gravar"]


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


def _gravar_novos(sessao: Session, propostos: Iterable[AlertaProposto]) -> list[Alerta]:
    """Grava os alertas propostos que ainda não existem (regra, alvo, assinatura)."""
    propostos = list(propostos)
    if not propostos:
        return []

    alvos = {p.alvo for p in propostos}
    existentes = {
        (regra, alvo, assin)
        for regra, alvo, assin in sessao.execute(
            select(Alerta.regra, Alerta.alvo, Alerta.assinatura).where(Alerta.alvo.in_(alvos))
        )
    }
    novos: list[Alerta] = []
    vistos: set[tuple[str, str, str]] = set()
    for p in propostos:
        chave = (p.regra, p.alvo, assinatura(p.eventos_ids))
        if chave not in existentes and chave not in vistos:
            vistos.add(chave)
            novos.append(_novo_alerta(p))
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


def gravar_alertas_do_evento(sessao: Session, evento: Evento, janela: timedelta) -> list[Alerta]:
    """Correlaciona o evento (já gravado) e grava os alertas que ainda não existem."""
    propostos = [
        p for p in correlacionar(_eventos_proximos(sessao, evento, janela), janela)
        if evento.id in p.eventos_ids
    ]
    return _gravar_novos(sessao, propostos)


# --- Saúde das fontes ------------------------------------------------------------


def _e_heartbeat():
    # O tipo chega sem espaços nas pontas (validação da API); falta só a caixa.
    return func.lower(Evento.tipo) == TIPO_HEARTBEAT


def _heartbeats_para_verificar(sessao: Session) -> list[Evento]:
    """Só o que a regra precisa, sem varrer o histórico inteiro na memória.

    Para cada (origem, alvo): o(s) heartbeat(s) mais recente(s) e, se a versão
    das regras for texto ou faltar, o heartbeat mais antigo com essa mesma
    versão (é ele que o alerta de desatualização cita; veja saude_fontes.py).
    """
    maximos = (
        select(Evento.origem, Evento.alvo, func.max(Evento.ocorrido_em).label("maximo"))
        .where(_e_heartbeat())
        .group_by(Evento.origem, Evento.alvo)
        .subquery()
    )
    ultimos = list(
        sessao.scalars(
            select(Evento)
            .join(
                maximos,
                and_(
                    Evento.origem == maximos.c.origem,
                    Evento.alvo == maximos.c.alvo,
                    Evento.ocorrido_em == maximos.c.maximo,
                ),
            )
            .where(_e_heartbeat())
        )
    )

    resultado = {e.id: e for e in ultimos}
    for ultimo in ultimos:
        detalhes = ultimo.detalhes if isinstance(ultimo.detalhes, dict) else {}
        versao = detalhes.get(CAMPO_VERSAO_REGRAS)
        campo = Evento.detalhes[CAMPO_VERSAO_REGRAS].as_string()
        if isinstance(versao, str):
            mesma_versao = campo == versao
        elif versao is None:
            mesma_versao = campo.is_(None)
        else:
            continue  # versão em formato estranho (número, lista): fica só o último
        primeiro = sessao.scalars(
            select(Evento)
            .where(
                _e_heartbeat(),
                Evento.origem == ultimo.origem,
                Evento.alvo == ultimo.alvo,
                mesma_versao,
            )
            .order_by(Evento.ocorrido_em, Evento.id)
            .limit(1)
        ).first()
        if primeiro is not None:
            resultado.setdefault(primeiro.id, primeiro)
    return list(resultado.values())


def verificar_saude_e_gravar(
    sessao: Session,
    agora: datetime,
    limite_silencio_horas: float,
    limite_desatualizacao_dias: float,
) -> list[Alerta]:
    """Roda a regra de saúde das fontes sobre os heartbeats do banco e grava os novos.

    `agora` vem de fora (o agendador passa a hora atual em UTC; os testes
    passam uma hora fixa). Erros não são tratados aqui: quem chama decide.
    Rodar duas vezes seguidas não duplica nada (mesmo dedupe da correlação).
    """
    propostos = verificar_saude(
        _heartbeats_para_verificar(sessao), agora,
        limite_silencio_horas=limite_silencio_horas,
        limite_desatualizacao_dias=limite_desatualizacao_dias,
    )
    return _gravar_novos(sessao, propostos)
