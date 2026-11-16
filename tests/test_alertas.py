"""Correlação de ponta a ponta: POST /eventos gera alertas, GET /alertas mostra."""

from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.alertas import assinatura, gravar_alertas_do_evento
from app.banco import Alerta, Evento


@pytest.fixture
def enviar(cliente, cabecalho, evento_valido):
    def _enviar(**mudancas):
        corpo = {**evento_valido, **mudancas}
        resposta = cliente.post("/eventos", json=corpo, headers=cabecalho)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()

    return _enviar


@pytest.fixture
def listar(cliente, cabecalho):
    def _listar(**params):
        resposta = cliente.get("/alertas", params=params, headers=cabecalho)
        assert resposta.status_code == 200, resposta.text
        return resposta.json()

    return _listar


def phishing_e_login(enviar, alvo="maria@x.com", login_em="2026-11-14T15:00:00Z"):
    p = enviar(alvo=alvo, nivel="ALTO")  # anzol, phishing_detectado, 10:00
    lf = enviar(origem="netsentinel", tipo="login_falho", nivel="MÉDIO", alvo=alvo,
                ocorrido_em=login_em, detalhes={})
    return p, lf


def test_evento_isolado_nao_gera_alerta(enviar, listar):
    enviar()
    assert listar() == []


def test_phishing_mais_login_gera_alerta_critico_explicavel(enviar, listar, cliente, cabecalho):
    p, lf = phishing_e_login(enviar)
    alertas = {a["regra"]: a for a in listar()}
    assert set(alertas) == {"phishing_mais_login_falho", "multiplas_fontes"}

    alerta = alertas["phishing_mais_login_falho"]
    assert alerta["nivel"] == "CRÍTICO"
    assert alerta["alvo"] == "maria@x.com"
    assert alerta["eventos_ids"] == [p["id"], lf["id"]]
    assert alerta["resumo"] and alerta["criado_em"]

    detalhe = cliente.get(f"/alertas/{alerta['id']}", headers=cabecalho)
    assert detalhe.status_code == 200
    assert [e["id"] for e in detalhe.json()["eventos"]] == [p["id"], lf["id"]]
    assert detalhe.json()["eventos"][0]["origem"] == "anzol"


def test_phishing_mais_login_fora_da_janela_nao_dispara(enviar, listar):
    phishing_e_login(enviar, login_em="2026-11-15T10:00:01Z")
    assert listar() == []


def test_janela_configuravel_pelo_ambiente(enviar, listar, monkeypatch):
    monkeypatch.setenv("ORBIT_JANELA_HORAS", "2")
    phishing_e_login(enviar)  # 5 h de diferença
    assert listar() == []


def test_evento_atrasado_conta_por_ocorrido_em(enviar, listar):
    # O login chega depois, mas aconteceu ANTES do phishing (ainda na janela).
    phishing_e_login(enviar, login_em="2026-11-14T08:00:00Z")
    assert "phishing_mais_login_falho" in {a["regra"] for a in listar()}


def test_alvos_diferentes_nao_se_misturam(enviar, listar):
    enviar(alvo="maria@x.com")
    enviar(origem="netsentinel", tipo="login_falho", alvo="joao@x.com")
    assert listar() == []


def test_alvo_com_maiusculas_correlaciona(enviar, listar):
    phishing_e_login(enviar, alvo=" Maria@X.com")
    enviar(origem="honeypot", tipo="acesso", alvo="MARIA@x.com", ocorrido_em="2026-11-14T16:00:00Z")
    assert {a["alvo"] for a in listar()} == {"maria@x.com"}


def test_rajada_via_api(enviar, listar):
    for minuto in ("00", "20", "40"):
        enviar(origem="netsentinel", tipo="varredura", nivel="ALTO",
               ocorrido_em=f"2026-11-14T10:{minuto}:00Z")
    assert [(a["regra"], a["nivel"]) for a in listar()] == [("rajada_de_alertas", "CRÍTICO")]


def test_alerta_duplicado_nao_e_criado(enviar, fabrica):
    _, lf = phishing_e_login(enviar)
    with fabrica() as sessao:
        antes = sessao.query(Alerta).count()
        assert antes == 2
        evento = sessao.get(Evento, lf["id"])
        # Rodar a correlação de novo para o mesmo evento não grava nada.
        assert gravar_alertas_do_evento(sessao, evento, timedelta(hours=24)) == []
        assert sessao.query(Alerta).count() == antes


def test_nivel_dos_alertas_gravados_nunca_desce(enviar, listar):
    enviar(nivel="ALTO")
    enviar(origem="netsentinel", tipo="varredura", nivel="ALTO", detalhes={})
    primeiro = listar()
    assert [a["nivel"] for a in primeiro] == ["CRÍTICO"]

    # Evento fraco de outra fonte: novo alerta continua CRÍTICO, o antigo não muda.
    enviar(origem="honeypot", tipo="acesso", nivel="BAIXO", ocorrido_em="2026-11-14T11:00:00Z")
    todos = {a["id"]: a for a in listar()}
    assert todos[primeiro[0]["id"]]["nivel"] == "CRÍTICO"
    assert {a["nivel"] for a in todos.values()} == {"CRÍTICO"}


def test_filtros_da_listagem_de_alertas(enviar, listar):
    phishing_e_login(enviar, alvo="maria@x.com")  # CRÍTICO + CRÍTICO
    enviar(origem="honeypot", tipo="acesso", nivel="BAIXO", alvo="joao@x.com")
    enviar(origem="logs", tipo="acesso", nivel="BAIXO", alvo="joao@x.com", detalhes={})  # MÉDIO

    assert len(listar()) == 3
    assert {a["alvo"] for a in listar(alvo="JOAO@x.com")} == {"joao@x.com"}
    assert {a["nivel"] for a in listar(nivel_minimo="ALTO")} == {"CRÍTICO"}
    assert len(listar(nivel_minimo="MÉDIO")) == 3
    assert len(listar(limite=1)) == 1


def test_limite_de_alertas_acima_de_200_da_422(cliente, cabecalho):
    assert cliente.get("/alertas", params={"limite": 201}, headers=cabecalho).status_code == 422


def test_alerta_inexistente_da_404(cliente, cabecalho):
    assert cliente.get("/alertas/999", headers=cabecalho).status_code == 404


def test_alertas_sem_chave_da_401(cliente):
    assert cliente.get("/alertas").status_code == 401
    assert cliente.get("/alertas/1").status_code == 401


def test_banco_recusa_alerta_duplicado_mesmo_em_corrida(fabrica):
    def alerta(ids):
        return Alerta(regra="multiplas_fontes", nivel="ALTO", alvo="a@x.com", resumo="r",
                      eventos_ids=ids, assinatura=assinatura(tuple(ids)))

    with fabrica() as sessao:
        sessao.add(alerta([1, 2]))
        sessao.commit()
        sessao.add(alerta([2, 1]))  # mesmo conjunto, outra ordem
        with pytest.raises(IntegrityError):
            sessao.commit()
