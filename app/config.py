"""Configuração do ORBIT, lida de variáveis de ambiente.

Nada de senha ou chave dentro do código: tudo vem do ambiente (.env no
desenvolvimento, variáveis do Docker Compose ou do servidor em produção).
"""

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
