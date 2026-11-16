import pytest

from app.config import JANELA_PADRAO_HORAS, janela_horas


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
