"""O evento normalizado: o formato único que toda fonte do ORBIT usa.

NetSentinel, Anzol, honeypot e scanner falam línguas diferentes. Para o ORBIT
correlacionar sinais de fontes distintas, todos precisam caber neste molde.
Veja docs/evento.md para a explicação completa.
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

TAMANHO_MAX_DETALHES = 8_192  # bytes; evita que alguém entupa o banco


class Origem(StrEnum):
    NETSENTINEL = "netsentinel"
    ANZOL = "anzol"
    HONEYPOT = "honeypot"
    SCANNER_SEGREDOS = "scanner_segredos"
    LOGS = "logs"


class Nivel(StrEnum):
    """Mesma escala do Anzol, da menor para a maior gravidade."""

    BAIXO = "BAIXO"
    MEDIO = "MÉDIO"
    ALTO = "ALTO"
    CRITICO = "CRÍTICO"


ORDEM_DOS_NIVEIS: list[Nivel] = [Nivel.BAIXO, Nivel.MEDIO, Nivel.ALTO, Nivel.CRITICO]


def niveis_a_partir_de(minimo: Nivel) -> list[Nivel]:
    """Todos os níveis iguais ou acima do mínimo (usado no filtro da listagem)."""
    return ORDEM_DOS_NIVEIS[ORDEM_DOS_NIVEIS.index(minimo) :]


class EventoEntrada(BaseModel):
    """O que uma fonte envia ao ORBIT."""

    model_config = ConfigDict(extra="forbid")

    origem: Origem
    tipo: str = Field(min_length=1, max_length=80, examples=["phishing_detectado"])
    alvo: str = Field(
        min_length=1,
        max_length=255,
        description="Quem ou o que foi alvo: usuário, e-mail, IP ou domínio.",
        examples=["maria@empresa.com.br"],
    )
    nivel: Nivel
    resumo: str = Field(min_length=1, max_length=500)
    ocorrido_em: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Quando o fato aconteceu (com fuso). Se omitido, vale agora.",
    )
    detalhes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tipo", "alvo", "resumo")
    @classmethod
    def _sem_espacos_nas_pontas(cls, valor: str) -> str:
        valor = valor.strip()
        if not valor:
            raise ValueError("não pode ficar vazio")
        return valor

    @field_validator("ocorrido_em")
    @classmethod
    def _exige_fuso(cls, valor: datetime) -> datetime:
        if valor.tzinfo is None:
            raise ValueError("informe o fuso horário (ex.: 2026-11-14T10:00:00Z)")
        return valor.astimezone(UTC)

    @field_validator("detalhes")
    @classmethod
    def _detalhes_pequenos(cls, valor: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(valor, ensure_ascii=False)) > TAMANHO_MAX_DETALHES:
            raise ValueError(f"detalhes passou de {TAMANHO_MAX_DETALHES} bytes")
        return valor


class EventoSaida(EventoEntrada):
    """O que o ORBIT devolve: o evento mais os campos que ele mesmo preenche."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    recebido_em: datetime
