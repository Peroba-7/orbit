"""Configuração do ORBIT, lida de variáveis de ambiente.

Nada de senha ou chave dentro do código: tudo vem do ambiente (.env no
desenvolvimento, variáveis do Docker Compose ou do servidor em produção).
"""

import math
import os


def url_do_banco() -> str:
    """Endereço do banco. Padrão: SQLite local, bom para desenvolver e testar."""
    return os.getenv("ORBIT_BANCO_URL", "sqlite:///./orbit.db")


def chave_da_api() -> str | None:
    """Chave que as fontes (NetSentinel, Anzol...) usam para enviar eventos.

    Se não estiver configurada, a API recusa tudo (falha fechada): é melhor
    parar do que aceitar eventos de qualquer um.
    """
    chave = os.getenv("ORBIT_CHAVE_API", "").strip()
    return chave or None


JANELA_PADRAO_HORAS = 24.0


def janela_horas() -> float:
    """Janela de correlação em horas (ORBIT_JANELA_HORAS, padrão 24).

    Aceita fração (ex.: 0.5). Valor inválido, zero, negativo ou infinito gera
    erro: uma janela errada faria o motor calar ou disparar à toa sem aviso.
    """
    bruto = os.getenv("ORBIT_JANELA_HORAS", "").strip()
    if not bruto:
        return JANELA_PADRAO_HORAS
    try:
        horas = float(bruto)
    except ValueError:
        raise ValueError(f"ORBIT_JANELA_HORAS precisa ser um número, veio {bruto!r}") from None
    if not math.isfinite(horas) or horas <= 0:
        raise ValueError(f"ORBIT_JANELA_HORAS precisa ser um número positivo, veio {bruto!r}")
    return horas
