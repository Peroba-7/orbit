"""Motor de correlação: regras fixas que juntam eventos do mesmo alvo em alertas.

Função pura: recebe eventos, devolve alertas propostos. Não lê nem grava banco
(quem grava é app/alertas.py), por isso é fácil de testar e de auditar.
Regras explicadas em docs/correlacao.md.

Como o conjunto de eventos de cada alerta é escolhido: cada evento serve de
"âncora" e a regra olha só para trás a partir dele, no intervalo
[âncora - janela, âncora], contado por `ocorrido_em`. Isso dá a cada alerta um
conjunto de eventos determinístico (o mesmo dado gera sempre o mesmo alerta),
o que permite evitar duplicatas.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.esquemas import ORDEM_DOS_NIVEIS, Nivel, Origem, normalizar_alvo

# --- Parâmetros das regras: edite aqui -------------------------------------

# Tipos de evento que contam em cada regra (comparados em minúsculas).
# TODO: conferir os tipos reais emitidos pelo NetSentinel.
TIPOS_PHISHING = {"phishing_detectado"}
TIPOS_LOGIN_FALHO = {"login_falho", "brute_force"}

ORIGEM_PHISHING = Origem.ANZOL
ORIGEM_LOGIN_FALHO = Origem.NETSENTINEL

RAJADA_JANELA = timedelta(hours=1)
RAJADA_MINIMO_DE_EVENTOS = 3
RAJADA_NIVEIS = {Nivel.ALTO, Nivel.CRITICO}

REGRA_PHISHING_MAIS_LOGIN = "phishing_mais_login_falho"
REGRA_RAJADA = "rajada_de_alertas"
REGRA_MULTIPLAS_FONTES = "multiplas_fontes"


class EventoCorrelacionavel(Protocol):
    """O mínimo que o motor precisa saber de um evento (o modelo do banco serve)."""

    id: int
    origem: str
    tipo: str
    alvo: str
    nivel: str
    ocorrido_em: datetime


@dataclass(frozen=True)
class AlertaProposto:
    regra: str
    nivel: Nivel
    alvo: str
    resumo: str
    eventos_ids: tuple[int, ...]  # ordenados, sem repetição


# --- Ajudantes ---------------------------------------------------------------


def _indice(nivel: str) -> int:
    return ORDEM_DOS_NIVEIS.index(Nivel(nivel))


def _maior_nivel(eventos: Iterable[EventoCorrelacionavel]) -> Nivel:
    return ORDEM_DOS_NIVEIS[max(_indice(e.nivel) for e in eventos)]


def _um_acima(nivel: Nivel) -> Nivel:
    return ORDEM_DOS_NIVEIS[min(ORDEM_DOS_NIVEIS.index(nivel) + 1, len(ORDEM_DOS_NIVEIS) - 1)]


def _tipo(evento: EventoCorrelacionavel) -> str:
    return evento.tipo.strip().lower()


def _e_phishing(evento: EventoCorrelacionavel) -> bool:
    return evento.origem == ORIGEM_PHISHING and _tipo(evento) in TIPOS_PHISHING


def _e_login_falho(evento: EventoCorrelacionavel) -> bool:
    return evento.origem == ORIGEM_LOGIN_FALHO and _tipo(evento) in TIPOS_LOGIN_FALHO


def _duracao(eventos: Sequence[EventoCorrelacionavel]) -> str:
    """Intervalo entre o primeiro e o último evento, em texto curto."""
    datas = [e.ocorrido_em for e in eventos]
    minutos = int((max(datas) - min(datas)).total_seconds() // 60)
    horas, minutos = divmod(minutos, 60)
    if horas and minutos:
        return f"{horas} h {minutos} min"
    if horas:
        return f"{horas} h"
    return f"{minutos} min"


def _antes_de(
    ancora: EventoCorrelacionavel, eventos: Sequence[EventoCorrelacionavel], janela: timedelta
) -> list[EventoCorrelacionavel]:
    """Eventos com ocorrido_em em [âncora - janela, âncora], incluindo a âncora."""
    inicio = ancora.ocorrido_em - janela
    return [e for e in eventos if inicio <= e.ocorrido_em <= ancora.ocorrido_em]


def _alerta(
    regra: str, nivel: Nivel, alvo: str, resumo: str, eventos: Iterable[EventoCorrelacionavel]
) -> AlertaProposto:
    ids = tuple(sorted({e.id for e in eventos}))
    return AlertaProposto(regra, nivel, alvo, resumo[:500], ids)


# --- Regras --------------------------------------------------------------------


def _phishing_mais_login_falho(
    ancora: EventoCorrelacionavel, janela_ev: list[EventoCorrelacionavel], alvo: str
) -> AlertaProposto | None:
    if _e_phishing(ancora):
        outros = [e for e in janela_ev if _e_login_falho(e)]
    elif _e_login_falho(ancora):
        outros = [e for e in janela_ev if _e_phishing(e)]
    else:
        return None
    if not outros:
        return None
    eventos = [ancora, *outros]
    phishing = sum(1 for e in eventos if _e_phishing(e))
    logins = len(eventos) - phishing
    resumo = (
        f"Phishing detectado pelo Anzol ({phishing} evento(s)) e falha de login vista "
        f"pelo NetSentinel ({logins} evento(s)) para o mesmo alvo em {_duracao(eventos)}: "
        "possível credencial roubada sendo testada."
    )
    return _alerta(REGRA_PHISHING_MAIS_LOGIN, Nivel.CRITICO, alvo, resumo, eventos)


def _rajada_de_alertas(
    ancora: EventoCorrelacionavel, eventos_do_alvo: list[EventoCorrelacionavel], alvo: str
) -> AlertaProposto | None:
    if Nivel(ancora.nivel) not in RAJADA_NIVEIS:
        return None
    graves = [
        e for e in _antes_de(ancora, eventos_do_alvo, RAJADA_JANELA)
        if Nivel(e.nivel) in RAJADA_NIVEIS
    ]
    if len(graves) < RAJADA_MINIMO_DE_EVENTOS:
        return None
    resumo = (
        f"{len(graves)} eventos ALTO ou CRÍTICO para o mesmo alvo em {_duracao(graves)} "
        f"(limite: {RAJADA_MINIMO_DE_EVENTOS} em 1 h): ataque em andamento ou insistente."
    )
    return _alerta(REGRA_RAJADA, Nivel.CRITICO, alvo, resumo, graves)


def _multiplas_fontes(
    janela_ev: list[EventoCorrelacionavel], alvo: str
) -> AlertaProposto | None:
    origens = sorted({e.origem for e in janela_ev})
    if len(origens) < 2:
        return None
    maior = _maior_nivel(janela_ev)
    nivel = _um_acima(maior)
    resumo = (
        f"{len(origens)} fontes diferentes ({', '.join(origens)}) viram o mesmo alvo em "
        f"{_duracao(janela_ev)}; maior nível dos eventos: {maior.value}, "
        f"alerta sobe para {nivel.value}."
    )
    return _alerta(REGRA_MULTIPLAS_FONTES, nivel, alvo, resumo, janela_ev)


# --- Entrada principal -----------------------------------------------------------


def correlacionar(
    eventos: Iterable[EventoCorrelacionavel], janela: timedelta
) -> list[AlertaProposto]:
    """Aplica todas as regras e devolve os alertas, sem repetição.

    Eventos de alvos diferentes nunca se misturam: o motor agrupa por alvo
    normalizado antes de aplicar as regras. Evento isolado não gera alerta.
    Garantia: o nível de todo alerta é maior ou igual ao maior nível dos seus
    eventos (o motor só sobe o risco, nunca desce).
    """
    if janela <= timedelta(0):
        raise ValueError("a janela precisa ser positiva")

    por_alvo: dict[str, list[EventoCorrelacionavel]] = defaultdict(list)
    for evento in eventos:
        por_alvo[normalizar_alvo(evento.alvo)].append(evento)

    alertas: dict[tuple[str, str, tuple[int, ...]], AlertaProposto] = {}
    for alvo, do_alvo in por_alvo.items():
        do_alvo.sort(key=lambda e: (e.ocorrido_em, e.id))
        for ancora in do_alvo:
            janela_ev = _antes_de(ancora, do_alvo, janela)
            candidatos = (
                _phishing_mais_login_falho(ancora, janela_ev, alvo),
                _rajada_de_alertas(ancora, do_alvo, alvo),
                _multiplas_fontes(janela_ev, alvo),
            )
            for alerta in candidatos:
                if alerta is not None:
                    alertas.setdefault((alerta.regra, alerta.alvo, alerta.eventos_ids), alerta)
    return list(alertas.values())
