"""Preparo dos dados do painel: funções puras, sem Streamlit e sem rede.

Recebem o JSON que a API devolve (listas de dicionários) e devolvem o que a
tela precisa: parâmetros de consulta, métricas, linhas de tabela e contagens.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

# Mesma escala da API (app/esquemas.py). Repetida aqui porque o painel roda em
# outro contêiner e só conversa com a API por HTTP.
NIVEIS = ["BAIXO", "MÉDIO", "ALTO", "CRÍTICO"]
ORIGENS = ["netsentinel", "anzol", "honeypot", "scanner_segredos", "logs"]
LIMITE_MAXIMO = 200

# Cores de fundo/texto de cada nível na tabela (contraste legível nos dois temas).
CORES_NIVEL = {
    "BAIXO": ("#d1e7dd", "#0f5132"),
    "MÉDIO": ("#fff3cd", "#664d03"),
    "ALTO": ("#ffe5d0", "#842029"),
    "CRÍTICO": ("#dc3545", "#ffffff"),
}

Registro = dict[str, Any]


def indice_nivel(nivel: str | None) -> int:
    """Posição do nível na escala; desconhecido fica abaixo de todos (-1)."""
    try:
        return NIVEIS.index(nivel or "")
    except ValueError:
        return -1


def normalizar_alvo(alvo: str | None) -> str | None:
    """Mesma regra da API: sem espaços nas pontas e em minúsculas. Vazio vira None."""
    if alvo is None:
        return None
    alvo = alvo.strip().lower()
    return alvo or None


def parametros(
    *,
    origem: str | None = None,
    nivel_minimo: str | None = None,
    alvo: str | None = None,
    limite: int = 50,
    para: str = "eventos",
) -> dict[str, Any]:
    """Monta os parâmetros de GET /eventos ou GET /alertas a partir dos filtros.

    Filtro vazio é omitido. O limite fica entre 1 e 200 (o máximo da API).
    `origem` só existe em /eventos: alerta não tem origem própria.
    """
    if para not in ("eventos", "alertas"):
        raise ValueError("para deve ser 'eventos' ou 'alertas'")
    params: dict[str, Any] = {"limite": max(1, min(int(limite), LIMITE_MAXIMO))}
    if nivel_minimo in NIVEIS:
        params["nivel_minimo"] = nivel_minimo
    alvo_normalizado = normalizar_alvo(alvo)
    if alvo_normalizado:
        params["alvo"] = alvo_normalizado
    if para == "eventos" and origem in ORIGENS:
        params["origem"] = origem
    return params


def filtrar(
    registros: Iterable[Registro],
    *,
    origem: str | None = None,
    nivel_minimo: str | None = None,
    alvo: str | None = None,
) -> list[Registro]:
    """Aplica os mesmos filtros localmente (rede de segurança sobre a resposta).

    `origem` só filtra registros que têm o campo `origem` (eventos).
    """
    minimo = indice_nivel(nivel_minimo) if nivel_minimo in NIVEIS else None
    alvo_normalizado = normalizar_alvo(alvo)
    resultado = []
    for r in registros:
        if origem and "origem" in r and r["origem"] != origem:
            continue
        if minimo is not None and indice_nivel(r.get("nivel")) < minimo:
            continue
        if alvo_normalizado and normalizar_alvo(r.get("alvo")) != alvo_normalizado:
            continue
        resultado.append(r)
    return resultado


def ler_data(texto: str | None) -> datetime | None:
    """Converte a data ISO da API para datetime em UTC (None se inválida)."""
    if not texto:
        return None
    try:
        data = datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None
    if data.tzinfo is None:
        data = data.replace(tzinfo=UTC)
    return data.astimezone(UTC)


def _data_ordenavel(texto: str | None) -> datetime:
    return ler_data(texto) or datetime.min.replace(tzinfo=UTC)


def ordenar_alertas(alertas: Iterable[Registro]) -> list[Registro]:
    """Do mais grave ao menos grave; no mesmo nível, do mais recente ao mais antigo."""
    return sorted(
        alertas,
        key=lambda a: (
            indice_nivel(a.get("nivel")),
            _data_ordenavel(a.get("criado_em")),
            a.get("id") or 0,
        ),
        reverse=True,
    )


def ordenar_eventos(eventos: Iterable[Registro]) -> list[Registro]:
    """Do mais recente ao mais antigo, por quando aconteceu (ocorrido_em)."""
    return sorted(
        eventos,
        key=lambda e: (_data_ordenavel(e.get("ocorrido_em")), e.get("id") or 0),
        reverse=True,
    )


def metricas(eventos: list[Registro], alertas: list[Registro]) -> dict[str, int]:
    """As 4 métricas do topo, sobre o que foi carregado."""
    alvos = {normalizar_alvo(r.get("alvo")) for r in [*eventos, *alertas]}
    alvos.discard(None)
    return {
        "eventos": len(eventos),
        "alertas": len(alertas),
        "alertas_criticos": sum(1 for a in alertas if a.get("nivel") == "CRÍTICO"),
        "alvos_distintos": len(alvos),
    }


def eventos_por_hora(eventos: Iterable[Registro]) -> list[Registro]:
    """Conta eventos por hora cheia (UTC) e origem, em ordem cronológica.

    Usa `ocorrido_em` (quando aconteceu), como o motor de correlação.
    Eventos com data inválida são ignorados.
    """
    contagem: Counter[tuple[datetime, str]] = Counter()
    for e in eventos:
        data = ler_data(e.get("ocorrido_em"))
        if data is None:
            continue
        hora = data.replace(minute=0, second=0, microsecond=0)
        contagem[(hora, str(e.get("origem") or "?"))] += 1
    return [
        {"hora": hora, "origem": origem, "eventos": n}
        for (hora, origem), n in sorted(contagem.items())
    ]


def linhas_alertas(alertas: Iterable[Registro]) -> list[Registro]:
    """Linhas da tabela de alertas, já na ordem de gravidade."""
    return [
        {
            "id": a.get("id"),
            "Nível": a.get("nivel"),
            "Regra": a.get("regra"),
            "Alvo": a.get("alvo"),
            "Resumo": a.get("resumo"),
            "Eventos": len(a.get("eventos_ids") or []),
            "Criado em (UTC)": ler_data(a.get("criado_em")),
        }
        for a in ordenar_alertas(alertas)
    ]


def linhas_eventos(eventos: Iterable[Registro]) -> list[Registro]:
    """Linhas da tabela de eventos, do mais recente ao mais antigo."""
    return [
        {
            "id": e.get("id"),
            "Ocorrido em (UTC)": ler_data(e.get("ocorrido_em")),
            "Nível": e.get("nivel"),
            "Origem": e.get("origem"),
            "Tipo": e.get("tipo"),
            "Alvo": e.get("alvo"),
            "Resumo": e.get("resumo"),
        }
        for e in ordenar_eventos(eventos)
    ]


def estilo_nivel(nivel: Any) -> str:
    """CSS de uma célula de nível (só para os 4 valores conhecidos)."""
    cores = CORES_NIVEL.get(nivel) if isinstance(nivel, str) else None
    if cores is None:
        return ""
    fundo, texto = cores
    return f"background-color: {fundo}; color: {texto}; font-weight: 600"
