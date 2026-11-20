"""Verificação de saúde contra o banco: busca heartbeats, grava alertas, sem duplicar.

Hora injetada (AGORA fixo) e banco em memória: nada de relógio nem de sleep.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.alertas import verificar_saude_e_gravar
from app.banco import Alerta, Evento
from app.saude_fontes import REGRA_DESATUALIZADA, REGRA_SILENCIOSA

AGORA = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)
EM_DIA = {"versao_regras": "2026-11-18"}
VELHA = {"versao_regras": "2026-10-01"}


@pytest.fixture
def sessao(fabrica):
    with fabrica() as s:
        yield s


@pytest.fixture
def gravar(sessao):
    def _gravar(horas_atras, alvo="sensor-sede", origem="netsentinel", tipo="heartbeat",
                detalhes=None, nivel="BAIXO"):
        evento = Evento(
            origem=origem, tipo=tipo, alvo=alvo, nivel=nivel, resumo="Sinal de vida.",
            detalhes=EM_DIA if detalhes is None else detalhes,
            ocorrido_em=AGORA - timedelta(hours=horas_atras),
        )
        sessao.add(evento)
        sessao.commit()
        return evento

    return _gravar


def verificar(sessao, agora=AGORA):
    return verificar_saude_e_gravar(
        sessao, agora, limite_silencio_horas=3, limite_desatualizacao_dias=7
    )


def total_de_alertas(sessao):
    return sessao.scalar(select(func.count()).select_from(Alerta))


def test_banco_sem_heartbeat_nao_gera_alerta(sessao, gravar):
    gravar(50, tipo="login_falho", alvo="maria@x.com", nivel="ALTO")
    assert verificar(sessao) == []
    assert total_de_alertas(sessao) == 0


def test_fonte_silenciosa_e_gravada(sessao, gravar):
    gravar(9)
    ultimo = gravar(5)
    gravados = verificar(sessao)
    assert [(a.regra, a.nivel, a.alvo, a.eventos_ids) for a in gravados] == [
        (REGRA_SILENCIOSA, "ALTO", "sensor-sede", [ultimo.id])
    ]
    assert gravados[0].id is not None


def test_heartbeat_recente_e_em_dia_nao_gera_alerta(sessao, gravar):
    gravar(30)
    gravar(0.5)  # o mais novo é o que vale
    assert verificar(sessao) == []


def test_tipo_heartbeat_em_maiusculas_conta(sessao, gravar):
    gravar(5, tipo="HeartBeat")
    assert [a.regra for a in verificar(sessao)] == [REGRA_SILENCIOSA]


def test_dedupe_em_duas_execucoes_seguidas(sessao, gravar):
    gravar(5)
    gravar(1, alvo="anzol-gateway", origem="anzol", detalhes=VELHA)
    primeira = verificar(sessao)
    assert sorted(a.regra for a in primeira) == [REGRA_DESATUALIZADA, REGRA_SILENCIOSA]

    assert verificar(sessao) == []
    assert verificar(sessao, AGORA + timedelta(minutes=5)) == []
    assert total_de_alertas(sessao) == 2


def test_desatualizada_nao_repete_a_cada_heartbeat(sessao, gravar):
    # Sensor desatualizado mandando sinal de vida a cada 5 min: um alerta só.
    primeiro = gravar(2, alvo="anzol-gateway", origem="anzol", detalhes=VELHA)
    assert [a.eventos_ids for a in verificar(sessao)] == [[primeiro.id]]
    for minutos in (55, 50, 45):
        gravar(minutos / 60, alvo="anzol-gateway", origem="anzol", detalhes=VELHA)
        assert verificar(sessao) == []
    assert total_de_alertas(sessao) == 1


def test_versao_desconhecida_tambem_nao_repete(sessao, gravar):
    gravar(2, detalhes={})
    assert len(verificar(sessao)) == 1
    gravar(1, detalhes={"outro": "campo"})
    assert verificar(sessao) == []


def test_sensor_atualizou_mas_ainda_velho_gera_alerta_novo(sessao, gravar):
    gravar(2, detalhes=VELHA)
    assert len(verificar(sessao)) == 1
    nova = gravar(1, detalhes={"versao_regras": "2026-10-20"})
    assert [a.eventos_ids for a in verificar(sessao)] == [[nova.id]]


def test_voltou_e_calou_de_novo_gera_alerta_novo(sessao, gravar):
    gravar(5)
    assert len(verificar(sessao)) == 1
    gravar(1)  # voltou
    assert verificar(sessao) == []
    # Calou de novo: 4 h depois, o último heartbeat (outro id) está velho.
    assert len(verificar(sessao, AGORA + timedelta(hours=4))) == 1
    assert total_de_alertas(sessao) == 2


def test_alerta_de_saude_aparece_em_get_alertas(cliente, cabecalho, sessao, gravar):
    heartbeat = gravar(5)
    verificar(sessao)

    alertas = cliente.get("/alertas", headers=cabecalho).json()
    assert [(a["regra"], a["alvo"], a["nivel"]) for a in alertas] == [
        (REGRA_SILENCIOSA, "sensor-sede", "ALTO")
    ]
    detalhe = cliente.get(f"/alertas/{alertas[0]['id']}", headers=cabecalho).json()
    assert [e["id"] for e in detalhe["eventos"]] == [heartbeat.id]
    assert detalhe["eventos"][0]["tipo"] == "heartbeat"
