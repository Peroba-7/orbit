"""Testes da regra de saúde das fontes (função pura, sem banco e sem relógio)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.esquemas import Nivel
from app.saude_fontes import (
    REGRA_DESATUALIZADA,
    REGRA_SILENCIOSA,
    ler_versao_regras,
    verificar_saude,
)

AGORA = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
VERSAO_EM_DIA = "2026-11-18"


@dataclass
class Ev:
    id: int
    ocorrido_em: datetime
    origem: str = "netsentinel"
    tipo: str = "heartbeat"
    alvo: str = "sensor-sede"
    nivel: str = "BAIXO"
    detalhes: dict[str, Any] | None = field(
        default_factory=lambda: {"versao_regras": VERSAO_EM_DIA}
    )


def hb(id, horas_atras, **kw):
    return Ev(id=id, ocorrido_em=AGORA - timedelta(hours=horas_atras), **kw)


def regras(alertas):
    return [(a.regra, a.alvo, a.nivel) for a in alertas]


# --- caminho feliz e casos vazios ------------------------------------------------


def test_heartbeat_recente_e_regras_em_dia_nao_gera_alerta():
    assert verificar_saude([hb(1, 0.5)], AGORA) == []


def test_sem_heartbeat_nenhum_nao_gera_alerta():
    assert verificar_saude([], AGORA) == []


def test_eventos_comuns_sem_heartbeat_nao_geram_alerta():
    # Eventos de segurança antigos não dizem nada sobre a saúde da fonte.
    eventos = [hb(1, 50, tipo="login_falho"), hb(2, 100, tipo="phishing_detectado")]
    assert verificar_saude(eventos, AGORA) == []


# --- silenciosa ------------------------------------------------------------------------


def test_fonte_silenciosa_gera_alerta_alto():
    alertas = verificar_saude([hb(7, 5)], AGORA)
    assert regras(alertas) == [(REGRA_SILENCIOSA, "sensor-sede", Nivel.ALTO)]
    assert alertas[0].resumo.startswith("sensor-sede sem sinal de vida há 5 h")
    assert alertas[0].eventos_ids == (7,)


def test_so_o_ultimo_heartbeat_conta():
    # Um heartbeat antigo não importa se já chegou um mais novo.
    assert verificar_saude([hb(1, 30), hb(2, 1), hb(3, 10)], AGORA) == []


def test_grupos_por_origem_e_alvo_normalizado():
    eventos = [
        hb(1, 1, alvo="Sensor-Sede "),         # mesmo grupo de id 2, e é o mais novo
        hb(2, 9, alvo="sensor-sede"),
        hb(3, 9, alvo="sensor-sede", origem="anzol"),  # outra origem: grupo próprio
    ]
    alertas = verificar_saude(eventos, AGORA)
    assert [a.eventos_ids for a in alertas] == [(3,)]
    assert "fonte anzol" in alertas[0].resumo


def test_silenciosa_nao_e_avaliada_como_desatualizada():
    alertas = verificar_saude([hb(1, 5, detalhes={})], AGORA)
    assert [a.regra for a in alertas] == [REGRA_SILENCIOSA]


# --- limite exato ------------------------------------------------------------------------


def test_silencio_exatamente_no_limite_ainda_esta_ok():
    assert verificar_saude([hb(1, 3)], AGORA, limite_silencio_horas=3) == []
    um_segundo_depois = AGORA + timedelta(seconds=1)
    assert [a.regra for a in verificar_saude([hb(1, 3)], um_segundo_depois)] == [
        REGRA_SILENCIOSA
    ]


def test_versao_exatamente_no_limite_ainda_esta_ok():
    no_limite = {"versao_regras": "2026-11-12"}  # 7 dias antes de AGORA
    assert verificar_saude([hb(1, 0, detalhes=no_limite)], AGORA) == []
    passou = {"versao_regras": "2026-11-11"}  # 8 dias
    assert [a.regra for a in verificar_saude([hb(1, 0, detalhes=passou)], AGORA)] == [
        REGRA_DESATUALIZADA
    ]


def test_limites_configuraveis():
    assert verificar_saude([hb(1, 5)], AGORA, limite_silencio_horas=6) == []
    velha = {"versao_regras": "2026-11-16"}  # 3 dias
    alertas = verificar_saude([hb(1, 0, detalhes=velha)], AGORA, limite_desatualizacao_dias=2)
    assert [a.regra for a in alertas] == [REGRA_DESATUALIZADA]


@pytest.mark.parametrize("valor", [0, -1, float("nan"), float("inf"), "3", True])
def test_limite_invalido_da_erro(valor):
    with pytest.raises(ValueError):
        verificar_saude([], AGORA, limite_silencio_horas=valor)
    with pytest.raises(ValueError):
        verificar_saude([], AGORA, limite_desatualizacao_dias=valor)


# --- desatualizada ------------------------------------------------------------------------


def test_regras_desatualizadas_geram_alerta_medio():
    alertas = verificar_saude([hb(4, 1, detalhes={"versao_regras": "2026-10-30"})], AGORA)
    assert regras(alertas) == [(REGRA_DESATUALIZADA, "sensor-sede", Nivel.MEDIO)]
    assert "versão 2026-10-30, de 20 dias atrás" in alertas[0].resumo


@pytest.mark.parametrize(
    "detalhes",
    [
        None,
        {},
        {"versao_regras": ""},
        {"versao_regras": "ontem"},
        {"versao_regras": "2026-02-30"},     # data que não existe
        {"versao_regras": "20261118"},       # sem hífens: fora do formato pedido
        {"versao_regras": "18/11/2026"},
        {"versao_regras": 20261118},
        {"versao_regras": ["2026-11-18"]},
        "não é dicionário",
    ],
)
def test_versao_ausente_ou_invalida_vira_desatualizacao_desconhecida(detalhes):
    alertas = verificar_saude([hb(1, 1, detalhes=detalhes)], AGORA)
    assert regras(alertas) == [(REGRA_DESATUALIZADA, "sensor-sede", Nivel.MEDIO)]
    assert "versão das regras é desconhecida" in alertas[0].resumo


def test_versao_com_espacos_nas_pontas_e_aceita():
    assert ler_versao_regras({"versao_regras": " 2026-11-18 "}).isoformat() == "2026-11-18"


def test_versao_no_futuro_nao_e_desatualizada():
    assert verificar_saude([hb(1, 0, detalhes={"versao_regras": "2026-12-01"})], AGORA) == []


# --- fuso horário ------------------------------------------------------------------------


def test_fuso_horario_do_heartbeat_e_do_agora():
    brasilia = timezone(timedelta(hours=-3))
    # 10:00 em Brasília = 13:00 UTC; agora = 15:00 UTC -> 2 h de silêncio: ok.
    evento = Ev(id=1, ocorrido_em=datetime(2026, 11, 19, 10, 0, tzinfo=brasilia))
    agora = datetime(2026, 11, 19, 15, 0, tzinfo=UTC)
    assert verificar_saude([evento], agora) == []
    # O mesmo instante expresso em outro fuso dá o mesmo resultado.
    assert verificar_saude([evento], agora.astimezone(brasilia)) == []
    # Lido como 10:00 UTC (ignorando o fuso) daria 5 h: seria alerta.
    assert regras(verificar_saude([evento], agora + timedelta(hours=2)))[0][0] == (
        REGRA_SILENCIOSA
    )


def test_idade_da_versao_conta_pela_data_em_utc():
    # 22:00 em Brasília do dia 19 já é dia 20 em UTC: versão de 12/11 passa a ter 8 dias.
    brasilia = timezone(timedelta(hours=-3))
    agora = datetime(2026, 11, 19, 22, 0, tzinfo=brasilia)
    evento = Ev(id=1, ocorrido_em=agora, detalhes={"versao_regras": "2026-11-12"})
    assert [a.regra for a in verificar_saude([evento], agora)] == [REGRA_DESATUALIZADA]


def test_heartbeat_sem_fuso_e_tratado_como_utc():
    evento = Ev(id=1, ocorrido_em=datetime(2026, 11, 19, 11, 0))  # 1 h antes, em UTC
    assert verificar_saude([evento], AGORA) == []


def test_agora_sem_fuso_da_erro():
    with pytest.raises(ValueError, match="fuso"):
        verificar_saude([], datetime(2026, 11, 19, 12, 0))


# --- dedupe ------------------------------------------------------------------------


def test_dedupe_mesmo_evento_repetido_gera_um_alerta():
    evento = hb(9, 5)
    alertas = verificar_saude([evento, evento, hb(9, 5)], AGORA)
    assert len(alertas) == 1


def test_dedupe_por_regra_alvo_e_assinatura():
    # Mesmo id em duas origens (dado inconsistente): mesma (regra, alvo, assinatura).
    alertas = verificar_saude([hb(9, 5), hb(9, 5, origem="anzol")], AGORA)
    assert len(alertas) == 1
    # Ids diferentes: assinaturas diferentes, dois alertas.
    assert len(verificar_saude([hb(9, 5), hb(10, 5, origem="anzol")], AGORA)) == 2


def test_tipo_heartbeat_ignora_maiusculas_e_espacos():
    assert len(verificar_saude([hb(1, 5, tipo=" HeartBeat ")], AGORA)) == 1
