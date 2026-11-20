"""Agendador da verificação de saúde: laço, erros, desligamento e lifespan da API.

Nada de sleep real: o laço recebe um `dormir` falso que conta as voltas e
cancela a tarefa quando o teste já viu o suficiente.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import agendador
from app.banco import Alerta, Evento
from app.main import app


def dormir_falso(voltas: int, esperas: list[float]):
    """Registra cada espera; na volta `voltas`+1 simula o desligamento (cancelamento)."""

    async def _dormir(segundos: float) -> None:
        esperas.append(segundos)
        if len(esperas) > voltas:
            raise asyncio.CancelledError

    return _dormir


# --- o laço -------------------------------------------------------------------------


def test_laco_espera_o_intervalo_antes_de_cada_verificacao():
    chamadas, esperas = [], []

    async def principal():
        await agendador.laco_de_verificacao(
            300, lambda: chamadas.append(len(esperas)), dormir_falso(3, esperas)
        )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(principal())
    assert esperas == [300, 300, 300, 300]
    # Cada verificação acontece DEPOIS de uma espera (nada na subida).
    assert chamadas == [1, 2, 3]


def test_erro_na_verificacao_nao_propaga_e_tenta_de_novo(caplog):
    chamadas, esperas = [], []

    def verificar():
        chamadas.append(1)
        if len(chamadas) == 1:
            raise RuntimeError("banco fora do ar")

    async def principal():
        await agendador.laco_de_verificacao(60, verificar, dormir_falso(3, esperas))

    # Só o cancelamento encerra o laço; o RuntimeError não escapa.
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(principal())
    assert len(chamadas) == 3
    assert "Falha na verificação de saúde" in caplog.text
    assert "banco fora do ar" in caplog.text


def test_executar_uma_vez_devolve_falso_no_erro():
    def quebra():
        raise ValueError("x")

    assert asyncio.run(agendador.executar_uma_vez(quebra)) is False
    assert asyncio.run(agendador.executar_uma_vez(lambda: None)) is True


def test_laco_recusa_intervalo_nao_positivo():
    with pytest.raises(ValueError):
        asyncio.run(agendador.laco_de_verificacao(0, lambda: None))


# --- iniciar e parar --------------------------------------------------------------------


def test_zero_minutos_desliga_e_parar_aceita_none():
    async def principal():
        tarefa = agendador.iniciar(0, lambda: None)
        await agendador.parar(tarefa)
        return tarefa

    assert asyncio.run(principal()) is None


def test_parar_cancela_a_tarefa_de_forma_limpa():
    async def principal():
        tarefa = agendador.iniciar(5, lambda: None)
        await asyncio.sleep(0)  # deixa a tarefa começar (e ficar esperando)
        await agendador.parar(tarefa)
        await agendador.parar(tarefa)  # parar de novo não quebra
        return tarefa

    tarefa = asyncio.run(principal())
    assert tarefa.cancelled()


# --- verificar_agora (com o banco em memória e a hora real) -------------------------------


def test_verificar_agora_grava_no_banco(monkeypatch, fabrica):
    monkeypatch.setattr(agendador, "FabricaDeSessao", fabrica)
    with fabrica() as sessao:
        sessao.add(Evento(
            origem="netsentinel", tipo="heartbeat", alvo="sensor-filial", nivel="BAIXO",
            resumo="Sinal de vida.", detalhes={"versao_regras": "2026-11-18"},
            ocorrido_em=datetime.now(UTC) - timedelta(hours=10),
        ))
        sessao.commit()

    assert agendador.verificar_agora(3, 7) == 1
    assert agendador.verificar_agora(3, 7) == 0  # dedupe
    with fabrica() as sessao:
        assert [a.regra for a in sessao.query(Alerta)] == ["fonte_silenciosa"]


# --- integração com o lifespan da API ------------------------------------------------------


@pytest.fixture
def espiao_do_laco(monkeypatch):
    """Troca o laço real por um que só registra se começou e se foi cancelado."""
    estado = {"iniciado": False, "cancelado": False, "intervalo": None}

    async def laco_falso(intervalo, verificar, dormir=None):
        estado["iniciado"] = True
        estado["intervalo"] = intervalo
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            estado["cancelado"] = True
            raise

    monkeypatch.setattr(agendador, "laco_de_verificacao", laco_falso)
    # Não toca no banco de verdade na subida.
    monkeypatch.setattr("app.main.criar_tabelas", lambda: None)
    monkeypatch.delenv("ORBIT_JANELA_HORAS", raising=False)
    return estado


def test_api_sobe_o_agendador_e_cancela_ao_desligar(monkeypatch, espiao_do_laco):
    monkeypatch.setenv("ORBIT_VERIFICACAO_MINUTOS", "2")
    with TestClient(app) as cliente:
        assert cliente.get("/saude").status_code == 200
        assert espiao_do_laco["iniciado"]
        assert espiao_do_laco["intervalo"] == 120
        assert not espiao_do_laco["cancelado"]
    assert espiao_do_laco["cancelado"]


def test_api_com_zero_minutos_nao_sobe_o_agendador(monkeypatch, espiao_do_laco):
    monkeypatch.setenv("ORBIT_VERIFICACAO_MINUTOS", "0")
    with TestClient(app) as cliente:
        assert cliente.get("/saude").status_code == 200
    assert not espiao_do_laco["iniciado"]


def test_api_com_intervalo_invalido_usa_o_padrao(monkeypatch, espiao_do_laco, caplog):
    monkeypatch.setenv("ORBIT_VERIFICACAO_MINUTOS", "abc")
    with TestClient(app):
        assert espiao_do_laco["intervalo"] == 5 * 60
    assert "ORBIT_VERIFICACAO_MINUTOS" in caplog.text
