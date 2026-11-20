"""Configuração do ORBIT, lida de variáveis de ambiente.

Nada de senha ou chave dentro do código: tudo vem do ambiente (.env no
desenvolvimento, variáveis do Docker Compose ou do servidor em produção).
"""

import logging
import math
import os

log = logging.getLogger(__name__)


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


# Saúde das fontes (app/saude_fontes.py). Ao contrário da janela, valor
# inválido NÃO impede a API de subir: cai no padrão e fica registrado no log.
# Errar aqui só muda quando o aviso de sensor parado aparece; parar a API por
# isso deixaria o ORBIT inteiro cego.
SILENCIO_PADRAO_HORAS = 3.0
DESATUALIZACAO_PADRAO_DIAS = 7


def _positivo_ou_padrao(nome: str, padrao: float, conversor) -> float:
    bruto = os.getenv(nome, "").strip()
    if not bruto:
        return padrao
    try:
        valor = conversor(bruto)
    except ValueError:
        valor = None
    if valor is None or not math.isfinite(valor) or valor <= 0:
        log.warning("%s inválido (%r): usando o padrão %s", nome, bruto, padrao)
        return padrao
    return valor


def silencio_horas() -> float:
    """Horas sem heartbeat até a fonte ser considerada silenciosa (ORBIT_SILENCIO_HORAS).

    Padrão 3. Aceita fração (ex.: 0.5). Inválido, zero ou negativo -> padrão.
    """
    return _positivo_ou_padrao("ORBIT_SILENCIO_HORAS", SILENCIO_PADRAO_HORAS, float)


def desatualizacao_dias() -> int:
    """Idade máxima da versão das regras, em dias (ORBIT_DESATUALIZACAO_DIAS).

    Padrão 7. Só número inteiro (a versão é uma data). Inválido, zero ou
    negativo -> padrão.
    """
    return int(
        _positivo_ou_padrao("ORBIT_DESATUALIZACAO_DIAS", DESATUALIZACAO_PADRAO_DIAS, int)
    )


VERIFICACAO_PADRAO_MINUTOS = 5.0


def verificacao_minutos() -> float:
    """Intervalo da verificação de saúde em segundo plano (ORBIT_VERIFICACAO_MINUTOS).

    Padrão 5. Aceita fração (ex.: 0.5). Zero desliga a verificação automática
    (útil em testes). Inválido, negativo ou infinito -> padrão, com aviso no log.
    """
    nome = "ORBIT_VERIFICACAO_MINUTOS"
    bruto = os.getenv(nome, "").strip()
    if not bruto:
        return VERIFICACAO_PADRAO_MINUTOS
    try:
        minutos = float(bruto)
    except ValueError:
        minutos = -1.0
    if not math.isfinite(minutos) or minutos < 0:
        log.warning("%s inválido (%r): usando o padrão %s", nome, bruto,
                    VERIFICACAO_PADRAO_MINUTOS)
        return VERIFICACAO_PADRAO_MINUTOS
    return minutos
