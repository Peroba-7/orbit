"""Saúde das fontes: avisa quando um sensor parou de falar ou está com regras velhas.

Um ORBIT sem alertas pode ser um dia tranquilo ou um sensor que caiu sem
ninguém ver. Para distinguir os dois, cada fonte envia de tempos em tempos um
evento do tipo "heartbeat" (sinal de vida). Esta regra olha esses sinais.

Função pura: recebe eventos e o "agora", devolve alertas propostos. Não lê
banco nem relógio, por isso é fácil de testar e de auditar.
Regras explicadas em docs/saude_fontes.md.
"""

import math
import re
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

from app.config import DESATUALIZACAO_PADRAO_DIAS, SILENCIO_PADRAO_HORAS
from app.correlacao import AlertaProposto, assinatura
from app.esquemas import Nivel, normalizar_alvo

# --- Parâmetros da regra: edite aqui ----------------------------------------

TIPO_HEARTBEAT = "heartbeat"
CAMPO_VERSAO_REGRAS = "versao_regras"

# Padrões; configuráveis por ORBIT_SILENCIO_HORAS e ORBIT_DESATUALIZACAO_DIAS
# (app/config.py), que quem chamar a função deve ler e repassar.
LIMITE_SILENCIO_HORAS_PADRAO = SILENCIO_PADRAO_HORAS
LIMITE_DESATUALIZACAO_DIAS_PADRAO = DESATUALIZACAO_PADRAO_DIAS

REGRA_SILENCIOSA = "fonte_silenciosa"
REGRA_DESATUALIZADA = "fonte_desatualizada"

NIVEL_SILENCIOSA = Nivel.ALTO
NIVEL_DESATUALIZADA = Nivel.MEDIO

_FORMATO_DATA = re.compile(r"\d{4}-\d{2}-\d{2}")


class EventoComDetalhes(Protocol):
    """O mínimo que a regra precisa de um evento (o modelo do banco serve)."""

    id: int
    origem: str
    tipo: str
    alvo: str
    ocorrido_em: datetime
    detalhes: dict[str, Any] | None


# --- Ajudantes ---------------------------------------------------------------


def _utc(data: datetime) -> datetime:
    """Converte para UTC. Data sem fuso é tratada como UTC (o banco grava em UTC)."""
    if data.tzinfo is None:
        return data.replace(tzinfo=UTC)
    return data.astimezone(UTC)


def _e_heartbeat(evento: EventoComDetalhes) -> bool:
    return evento.tipo.strip().lower() == TIPO_HEARTBEAT


def _texto_duracao(duracao: timedelta) -> str:
    """Duração em texto curto, arredondada para baixo: '5 h', '3 h 20 min', '2 dias 4 h'."""
    minutos = int(duracao.total_seconds() // 60)
    horas, minutos = divmod(minutos, 60)
    if horas >= 48:
        dias, horas = divmod(horas, 24)
        return f"{dias} dias {horas} h" if horas else f"{dias} dias"
    if horas and minutos:
        return f"{horas} h {minutos} min"
    if horas:
        return f"{horas} h"
    return f"{minutos} min"


def _texto_numero(valor: float) -> str:
    return str(int(valor)) if float(valor).is_integer() else str(valor)


def ler_versao_regras(detalhes: Any) -> date | None:
    """Lê detalhes["versao_regras"] no formato AAAA-MM-DD. None se faltar ou for inválida."""
    if not isinstance(detalhes, dict):
        return None
    bruto = detalhes.get(CAMPO_VERSAO_REGRAS)
    if not isinstance(bruto, str) or not _FORMATO_DATA.fullmatch(bruto.strip()):
        return None
    try:
        return date.fromisoformat(bruto.strip())
    except ValueError:  # ex.: 2026-02-30
        return None


def _validar_limites(silencio_horas: float, desatualizacao_dias: float) -> None:
    for nome, valor in (
        ("limite_silencio_horas", silencio_horas),
        ("limite_desatualizacao_dias", desatualizacao_dias),
    ):
        if isinstance(valor, bool) or not isinstance(valor, int | float):
            raise ValueError(f"{nome} precisa ser um número")
        if not math.isfinite(valor) or valor <= 0:
            raise ValueError(f"{nome} precisa ser um número positivo")


# --- Regras --------------------------------------------------------------------


def _silenciosa(
    ultimo: EventoComDetalhes, origem: str, alvo: str, agora: datetime, limite: timedelta,
    limite_horas: float,
) -> AlertaProposto | None:
    silencio = agora - _utc(ultimo.ocorrido_em)
    if silencio <= limite:  # exatamente no limite ainda está ok
        return None
    resumo = (
        f"{alvo} sem sinal de vida há {_texto_duracao(silencio)} "
        f"(fonte {origem}; limite: {_texto_numero(limite_horas)} h). "
        "O sensor pode ter caído: enquanto isso, ataques a ele não aparecem no ORBIT."
    )
    return _alerta(REGRA_SILENCIOSA, NIVEL_SILENCIOSA, alvo, resumo, ultimo)


def _desatualizada(
    ultimo: EventoComDetalhes, origem: str, alvo: str, agora: datetime, limite_dias: float,
) -> AlertaProposto | None:
    versao = ler_versao_regras(ultimo.detalhes)
    if versao is None:
        resumo = (
            f"{alvo} manda sinal de vida, mas a versão das regras é desconhecida "
            f"(fonte {origem}): o heartbeat não trouxe '{CAMPO_VERSAO_REGRAS}' "
            "no formato AAAA-MM-DD. Não dá para saber se as regras estão em dia."
        )
        return _alerta(REGRA_DESATUALIZADA, NIVEL_DESATUALIZADA, alvo, resumo, ultimo)

    idade_dias = (agora.date() - versao).days
    if idade_dias <= limite_dias:  # exatamente no limite ainda está ok
        return None
    resumo = (
        f"{alvo} com regras desatualizadas: versão {versao.isoformat()}, "
        f"de {idade_dias} dias atrás (fonte {origem}; limite: "
        f"{_texto_numero(limite_dias)} dias). Ameaças novas podem passar sem detecção."
    )
    return _alerta(REGRA_DESATUALIZADA, NIVEL_DESATUALIZADA, alvo, resumo, ultimo)


def _alerta(
    regra: str, nivel: Nivel, alvo: str, resumo: str, evento: EventoComDetalhes
) -> AlertaProposto:
    return AlertaProposto(regra, nivel, alvo, resumo[:500], (evento.id,))


# --- Entrada principal -----------------------------------------------------------


def verificar_saude(
    eventos: Iterable[EventoComDetalhes],
    agora: datetime,
    limite_silencio_horas: float = LIMITE_SILENCIO_HORAS_PADRAO,
    limite_desatualizacao_dias: float = LIMITE_DESATUALIZACAO_DIAS_PADRAO,
) -> list[AlertaProposto]:
    """Verifica o último heartbeat de cada fonte e devolve os alertas de saúde.

    - Só eventos do tipo "heartbeat" contam; os outros são ignorados. Sem
      heartbeat nenhum, não há alerta (não dá para saber quais fontes existem).
    - Agrupa por (origem, alvo normalizado) e olha só o heartbeat mais recente
      de cada grupo.
    - Silenciosa: último heartbeat mais antigo que o limite -> ALTO.
    - Desatualizada: heartbeat recente, mas detalhes["versao_regras"] mais
      velha que o limite, ausente ou inválida -> MÉDIO.
    - Exatamente no limite ainda está ok (só passa do limite se for maior).

    `agora` precisa ter fuso (é a referência de tudo). A idade das regras é
    contada em dias de calendário, pela data de `agora` em UTC.
    Sem duplicatas: mesma (regra, alvo, assinatura) aparece uma vez só.
    """
    if agora.tzinfo is None:
        raise ValueError("agora precisa ter fuso horário")
    _validar_limites(limite_silencio_horas, limite_desatualizacao_dias)
    agora = agora.astimezone(UTC)
    limite_silencio = timedelta(hours=limite_silencio_horas)

    ultimos: dict[tuple[str, str], EventoComDetalhes] = {}
    for evento in eventos:
        if not _e_heartbeat(evento):
            continue
        chave = (str(evento.origem), normalizar_alvo(evento.alvo))
        atual = ultimos.get(chave)
        if atual is None or (_utc(evento.ocorrido_em), evento.id) > (
            _utc(atual.ocorrido_em), atual.id
        ):
            ultimos[chave] = evento

    alertas: dict[tuple[str, str, str], AlertaProposto] = {}
    for (origem, alvo), ultimo in sorted(ultimos.items()):
        alerta = _silenciosa(ultimo, origem, alvo, agora, limite_silencio, limite_silencio_horas)
        if alerta is None:
            alerta = _desatualizada(ultimo, origem, alvo, agora, limite_desatualizacao_dias)
        if alerta is not None:
            chave_alerta = (alerta.regra, alerta.alvo, assinatura(alerta.eventos_ids))
            alertas.setdefault(chave_alerta, alerta)
    return list(alertas.values())

