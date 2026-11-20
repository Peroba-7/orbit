import pytest

from app.config import (
    DESATUALIZACAO_PADRAO_DIAS,
    JANELA_PADRAO_HORAS,
    SILENCIO_PADRAO_HORAS,
    VERIFICACAO_PADRAO_MINUTOS,
    desatualizacao_dias,
    janela_horas,
    silencio_horas,
    verificacao_minutos,
)


def test_janela_padrao_e_24_horas(monkeypatch):
    monkeypatch.delenv("ORBIT_JANELA_HORAS", raising=False)
    assert janela_horas() == JANELA_PADRAO_HORAS == 24


def test_janela_configuravel_aceita_fracao(monkeypatch):
    monkeypatch.setenv("ORBIT_JANELA_HORAS", "0.5")
    assert janela_horas() == 0.5


@pytest.mark.parametrize("valor", ["0", "-3", "abc", "nan", "inf"])
def test_janela_invalida_da_erro(monkeypatch, valor):
    monkeypatch.setenv("ORBIT_JANELA_HORAS", valor)
    with pytest.raises(ValueError, match="ORBIT_JANELA_HORAS"):
        janela_horas()


# --- saúde das fontes: inválido cai no padrão (não derruba a API) ---------------


def test_limites_de_saude_padrao(monkeypatch):
    monkeypatch.delenv("ORBIT_SILENCIO_HORAS", raising=False)
    monkeypatch.delenv("ORBIT_DESATUALIZACAO_DIAS", raising=False)
    assert silencio_horas() == SILENCIO_PADRAO_HORAS == 3
    assert desatualizacao_dias() == DESATUALIZACAO_PADRAO_DIAS == 7


def test_limites_de_saude_configuraveis(monkeypatch):
    monkeypatch.setenv("ORBIT_SILENCIO_HORAS", " 0.5 ")
    monkeypatch.setenv("ORBIT_DESATUALIZACAO_DIAS", "14")
    assert silencio_horas() == 0.5
    assert desatualizacao_dias() == 14


@pytest.mark.parametrize("valor", ["0", "-3", "abc", "nan", "inf", "-inf"])
def test_silencio_invalido_cai_no_padrao(monkeypatch, caplog, valor):
    monkeypatch.setenv("ORBIT_SILENCIO_HORAS", valor)
    assert silencio_horas() == SILENCIO_PADRAO_HORAS
    assert "ORBIT_SILENCIO_HORAS" in caplog.text


@pytest.mark.parametrize("valor", ["0", "-1", "abc", "2.5", "nan", "7 dias"])
def test_desatualizacao_invalida_cai_no_padrao(monkeypatch, caplog, valor):
    monkeypatch.setenv("ORBIT_DESATUALIZACAO_DIAS", valor)
    assert desatualizacao_dias() == DESATUALIZACAO_PADRAO_DIAS
    assert "ORBIT_DESATUALIZACAO_DIAS" in caplog.text


# --- intervalo da verificação de saúde ---------------------------------------------


def test_verificacao_padrao_e_5_minutos(monkeypatch):
    monkeypatch.delenv("ORBIT_VERIFICACAO_MINUTOS", raising=False)
    assert verificacao_minutos() == VERIFICACAO_PADRAO_MINUTOS == 5


@pytest.mark.parametrize(("valor", "esperado"), [("10", 10), (" 0.5 ", 0.5), ("0", 0)])
def test_verificacao_configuravel_e_zero_desliga(monkeypatch, valor, esperado):
    monkeypatch.setenv("ORBIT_VERIFICACAO_MINUTOS", valor)
    assert verificacao_minutos() == esperado


@pytest.mark.parametrize("valor", ["-1", "abc", "nan", "inf", "5 min"])
def test_verificacao_invalida_cai_no_padrao(monkeypatch, caplog, valor):
    monkeypatch.setenv("ORBIT_VERIFICACAO_MINUTOS", valor)
    assert verificacao_minutos() == VERIFICACAO_PADRAO_MINUTOS
    assert "ORBIT_VERIFICACAO_MINUTOS" in caplog.text
