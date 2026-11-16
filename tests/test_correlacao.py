"""Testes da função pura de correlação (sem banco, sem API)."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from app.correlacao import (
    REGRA_MULTIPLAS_FONTES,
    REGRA_PHISHING_MAIS_LOGIN,
    REGRA_RAJADA,
    correlacionar,
)
from app.esquemas import ORDEM_DOS_NIVEIS, Nivel

JANELA = timedelta(hours=24)
T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)
_ids = count(1)


@dataclass
class Ev:
    origem: str
    tipo: str
    nivel: str
    ocorrido_em: datetime
    alvo: str = "maria@x.com"
    id: int = 0

    def __post_init__(self):
        self.id = self.id or next(_ids)


def phishing(horas=0.0, **kw):
    return Ev("anzol", "phishing_detectado", kw.pop("nivel", "ALTO"),
              T0 + timedelta(hours=horas), **kw)


def login_falho(horas=0.0, **kw):
    return Ev("netsentinel", kw.pop("tipo", "login_falho"), kw.pop("nivel", "MÉDIO"),
              T0 + timedelta(hours=horas), **kw)


def ev(origem="netsentinel", nivel="ALTO", horas=0.0, **kw):
    return Ev(origem, kw.pop("tipo", "varredura"), nivel, T0 + timedelta(hours=horas), **kw)


def por_regra(alertas, regra):
    return [a for a in alertas if a.regra == regra]


# --- evento isolado -------------------------------------------------------------


def test_evento_isolado_nao_gera_alerta():
    assert correlacionar([phishing(nivel="CRÍTICO")], JANELA) == []


def test_lista_vazia_nao_gera_alerta():
    assert correlacionar([], JANELA) == []


# --- phishing_mais_login_falho ----------------------------------------------------


@pytest.mark.parametrize("tipo_login", ["login_falho", "brute_force"])
def test_phishing_mais_login_dentro_da_janela_e_critico(tipo_login):
    p, lf = phishing(0), login_falho(5, tipo=tipo_login)
    alertas = por_regra(correlacionar([p, lf], JANELA), REGRA_PHISHING_MAIS_LOGIN)
    assert len(alertas) == 1
    assert alertas[0].nivel == Nivel.CRITICO
    assert alertas[0].eventos_ids == tuple(sorted((p.id, lf.id)))
    assert "Phishing" in alertas[0].resumo


def test_phishing_mais_login_vale_em_qualquer_ordem():
    alertas = correlacionar([login_falho(0), phishing(3)], JANELA)
    assert len(por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN)) == 1


def test_phishing_mais_login_no_limite_exato_da_janela_dispara():
    alertas = correlacionar([phishing(0), login_falho(24)], JANELA)
    assert len(por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN)) == 1


def test_phishing_mais_login_fora_da_janela_nao_dispara():
    alertas = correlacionar([phishing(0), login_falho(24.01)], JANELA)
    assert por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN) == []


def test_phishing_mais_login_respeita_janela_configurada():
    alertas = correlacionar([phishing(0), login_falho(3)], timedelta(hours=2))
    assert por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN) == []


def test_mesma_origem_nao_dispara_phishing_mais_login():
    # Anzol mandando "login_falho" não é o NetSentinel vendo login falho.
    p = phishing(0)
    falso_login = Ev("anzol", "login_falho", "ALTO", T0 + timedelta(hours=1))
    assert correlacionar([p, falso_login], JANELA) == []  # mesma origem: nada


def test_tipo_errado_nao_dispara_phishing_mais_login():
    alertas = correlacionar([phishing(0), login_falho(1, tipo="varredura_de_portas")], JANELA)
    assert por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN) == []


def test_ordem_dos_dados_de_entrada_nao_importa():
    eventos = [phishing(0), login_falho(1), ev("honeypot", horas=2)]
    assert set(correlacionar(eventos, JANELA)) == set(correlacionar(eventos[::-1], JANELA))


def test_janela_conta_por_ocorrido_em():
    # Chegaram juntos, mas aconteceram com 30 h de diferença: fora da janela.
    alertas = correlacionar([login_falho(30), phishing(0)], JANELA)
    assert alertas == []


# --- rajada_de_alertas ----------------------------------------------------------------


def test_dois_eventos_altos_nao_formam_rajada():
    alertas = correlacionar([ev(horas=0), ev(horas=0.2)], JANELA)
    assert por_regra(alertas, REGRA_RAJADA) == []


def test_tres_eventos_altos_ou_criticos_em_uma_hora_formam_rajada():
    eventos = [ev(horas=0), ev(nivel="CRÍTICO", horas=0.5), ev(horas=1)]
    alertas = por_regra(correlacionar(eventos, JANELA), REGRA_RAJADA)
    assert len(alertas) == 1
    assert alertas[0].nivel == Nivel.CRITICO
    assert alertas[0].eventos_ids == tuple(sorted(e.id for e in eventos))


def test_rajada_espalhada_por_mais_de_uma_hora_nao_dispara():
    eventos = [ev(horas=0), ev(horas=0.7), ev(horas=1.4)]  # nunca 3 dentro de 1 h
    assert por_regra(correlacionar(eventos, JANELA), REGRA_RAJADA) == []


def test_eventos_baixos_e_medios_nao_contam_para_rajada():
    eventos = [ev(horas=0), ev(horas=0.1), ev(nivel="MÉDIO", horas=0.2), ev(nivel="BAIXO")]
    assert por_regra(correlacionar(eventos, JANELA), REGRA_RAJADA) == []


# --- multiplas_fontes -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("maior", "esperado"),
    [("BAIXO", "MÉDIO"), ("MÉDIO", "ALTO"), ("ALTO", "CRÍTICO"), ("CRÍTICO", "CRÍTICO")],
)
def test_multiplas_fontes_sobe_um_nivel_acima_do_maior(maior, esperado):
    eventos = [ev("honeypot", nivel="BAIXO", horas=0), ev("netsentinel", nivel=maior, horas=2)]
    alertas = por_regra(correlacionar(eventos, JANELA), REGRA_MULTIPLAS_FONTES)
    assert len(alertas) == 1
    assert alertas[0].nivel == Nivel(esperado)


def test_multiplas_fontes_fora_da_janela_nao_dispara():
    eventos = [ev("honeypot", horas=0), ev("netsentinel", horas=25)]
    assert correlacionar(eventos, JANELA) == []


def test_mesma_fonte_repetida_nao_e_multiplas_fontes():
    eventos = [ev("honeypot", nivel="BAIXO", horas=h) for h in (0, 2, 4)]
    assert correlacionar(eventos, JANELA) == []


# --- regras gerais ------------------------------------------------------------------------


def test_alvos_diferentes_nao_se_misturam():
    eventos = [
        phishing(0, alvo="maria@x.com"),
        login_falho(1, alvo="joao@x.com"),
        ev(horas=0, alvo="a@x.com"), ev(horas=0.1, alvo="b@x.com"), ev(horas=0.2, alvo="c@x.com"),
    ]
    assert correlacionar(eventos, JANELA) == []


def test_alvo_com_maiusculas_e_espacos_e_o_mesmo_alvo():
    alertas = correlacionar([phishing(0, alvo="Maria@X.com "), login_falho(1)], JANELA)
    assert {a.alvo for a in alertas} == {"maria@x.com"}
    assert len(por_regra(alertas, REGRA_PHISHING_MAIS_LOGIN)) == 1


def test_nao_devolve_alerta_repetido():
    # Dois eventos no mesmo instante geram a mesma janela a partir das duas âncoras.
    alertas = correlacionar([ev("honeypot", horas=0), ev("netsentinel", horas=0)], JANELA)
    chaves = [(a.regra, a.alvo, a.eventos_ids) for a in alertas]
    assert len(chaves) == len(set(chaves)) == 1


def test_nivel_do_alerta_nunca_fica_abaixo_dos_eventos():
    eventos = [
        phishing(0, nivel="CRÍTICO"), login_falho(1, nivel="BAIXO"), ev("honeypot", "MÉDIO", 2),
        ev(horas=2.1), ev(nivel="CRÍTICO", horas=2.2), ev("logs", "BAIXO", 30),
    ]
    por_id = {e.id: e for e in eventos}
    alertas = correlacionar(eventos, JANELA)
    assert alertas
    for alerta in alertas:
        maior = max(ORDEM_DOS_NIVEIS.index(Nivel(por_id[i].nivel)) for i in alerta.eventos_ids)
        assert ORDEM_DOS_NIVEIS.index(alerta.nivel) >= maior


def test_evento_mais_fraco_depois_nao_baixa_o_nivel():
    antes = [ev("anzol", "ALTO", 0), ev("netsentinel", "ALTO", 1)]
    depois = [*antes, ev("honeypot", "BAIXO", 2)]
    nivel_antes = por_regra(correlacionar(antes, JANELA), REGRA_MULTIPLAS_FONTES)[0].nivel
    novos = por_regra(correlacionar(depois, JANELA), REGRA_MULTIPLAS_FONTES)
    assert nivel_antes == Nivel.CRITICO
    assert all(a.nivel == Nivel.CRITICO for a in novos)


def test_janela_nao_positiva_e_recusada():
    with pytest.raises(ValueError):
        correlacionar([], timedelta(0))
