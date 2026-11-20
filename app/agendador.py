"""Verificação de saúde das fontes em segundo plano, dentro da própria API.

Uma fonte calada não manda evento, então a verificação não pode depender do
POST /eventos: uma tarefa asyncio roda `verificar_saude_e_gravar` a cada
ORBIT_VERIFICACAO_MINUTOS (padrão 5; 0 desliga). Ela nasce e morre com a API
(lifespan em app/main.py). Detalhes em docs/saude_fontes.md.

Regras desta tarefa:
- Uma falha numa verificação NUNCA derruba a API: o erro vai para o log e a
  próxima tentativa acontece no ciclo seguinte.
- O primeiro ciclo roda só depois de um intervalo, não na subida: se a API
  ficou fora do ar, as fontes ganham tempo de mandar heartbeat antes de serem
  julgadas silenciosas (senão toda reinicialização viraria uma chuva de alertas).
- O banco é síncrono: a verificação roda numa thread para não travar as
  requisições enquanto consulta.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from datetime import UTC, datetime

from app.alertas import verificar_saude_e_gravar
from app.banco import FabricaDeSessao

log = logging.getLogger(__name__)

Dormir = Callable[[float], Awaitable[object]]


def verificar_agora(limite_silencio_horas: float, limite_desatualizacao_dias: float) -> int:
    """Uma verificação completa, com a hora atual em UTC. Devolve quantos alertas gravou."""
    with FabricaDeSessao() as sessao:
        novos = verificar_saude_e_gravar(
            sessao, datetime.now(UTC),
            limite_silencio_horas=limite_silencio_horas,
            limite_desatualizacao_dias=limite_desatualizacao_dias,
        )
    for alerta in novos:
        log.warning("Saúde das fontes: alerta %s (%s) para %s",
                    alerta.regra, alerta.nivel, alerta.alvo)
    return len(novos)


async def executar_uma_vez(verificar: Callable[[], object]) -> bool:
    """Roda uma verificação numa thread. Erro vira log, nunca exceção. True se deu certo.

    Cancelamento (desligamento da API) não é engolido: CancelledError não é
    Exception, então sobe normalmente.
    """
    try:
        await asyncio.to_thread(verificar)
    except Exception:
        log.exception("Falha na verificação de saúde das fontes; "
                      "nova tentativa no próximo ciclo.")
        return False
    return True


async def laco_de_verificacao(
    intervalo_segundos: float,
    verificar: Callable[[], object],
    dormir: Dormir = asyncio.sleep,
) -> None:
    """Espera um intervalo, verifica, repete, até ser cancelado."""
    if intervalo_segundos <= 0:
        raise ValueError("o intervalo precisa ser positivo")
    while True:
        await dormir(intervalo_segundos)
        await executar_uma_vez(verificar)


def iniciar(minutos: float, verificar: Callable[[], object]) -> asyncio.Task | None:
    """Cria a tarefa de fundo. Com 0 minutos, não cria nada (verificação desligada)."""
    if minutos <= 0:
        log.info("Verificação de saúde das fontes desligada (ORBIT_VERIFICACAO_MINUTOS=0).")
        return None
    log.info("Verificação de saúde das fontes a cada %s min.", minutos)
    return asyncio.create_task(
        laco_de_verificacao(minutos * 60, verificar), name="orbit-verificacao-saude"
    )


async def parar(tarefa: asyncio.Task | None) -> None:
    """Cancela a tarefa e espera ela terminar. Seguro com None ou tarefa já encerrada.

    Se uma verificação estiver no meio, a thread dela termina sozinha (threads
    não são interrompidas); o que ela gravar segue as mesmas regras de dedupe.
    """
    if tarefa is None:
        return
    tarefa.cancel()
    with suppress(asyncio.CancelledError):
        await tarefa
