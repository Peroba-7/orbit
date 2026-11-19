"""Os dados de demonstração são válidos, fictícios e disparam os cenários prometidos."""

import ipaddress
from datetime import UTC, datetime
from types import SimpleNamespace

from app.esquemas import EventoEntrada
from app.saude_fontes import REGRA_DESATUALIZADA, REGRA_SILENCIOSA, verificar_saude
from scripts.popular_demo import eventos_demo, main

FAIXAS_RESERVADAS = [
    ipaddress.ip_network(r) for r in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")
]


def _e_ip(texto):
    try:
        return ipaddress.ip_address(texto)
    except ValueError:
        return None


def test_cerca_de_35_eventos_validos_de_anzol_e_netsentinel():
    eventos = eventos_demo()
    assert 30 <= len(eventos) <= 40
    for evento in eventos:
        EventoEntrada.model_validate(evento)  # mesmo molde que a API exige
    assert {e["origem"] for e in eventos} == {"anzol", "netsentinel"}


def test_so_usa_ips_reservados_e_dominio_de_exemplo():
    for evento in eventos_demo():
        textos = [evento["alvo"], *map(str, evento["detalhes"].values())]
        for texto in textos:
            ip = _e_ip(texto)
            if ip is not None:
                assert any(ip in faixa for faixa in FAIXAS_RESERVADAS), texto
        if "@" in evento["alvo"]:
            assert evento["alvo"].endswith("@exemplo.com.br")


def test_cenarios_disparam_os_alertas_esperados(cliente, cabecalho):
    for evento in eventos_demo(datetime(2026, 11, 14, 12, tzinfo=UTC)):
        assert cliente.post("/eventos", json=evento, headers=cabecalho).status_code == 201

    alertas = cliente.get("/alertas", params={"limite": 200}, headers=cabecalho).json()
    por_regra = {}
    for a in alertas:
        por_regra.setdefault(a["regra"], set()).add(a["alvo"])

    assert por_regra["phishing_mais_login_falho"] == {"maria@exemplo.com.br"}
    assert por_regra["rajada_de_alertas"] == {"203.0.113.45"}
    # Os eventos isolados não geram nada: só os dois alvos dos cenários aparecem.
    assert {a["alvo"] for a in alertas} == {"maria@exemplo.com.br", "203.0.113.45"}


def test_sem_chave_nao_envia(monkeypatch, capsys):
    monkeypatch.delenv("ORBIT_CHAVE_API", raising=False)
    assert main(["--sim"]) == 2
    assert "ORBIT_CHAVE_API" in capsys.readouterr().err


def test_sem_confirmacao_nao_envia(monkeypatch, capsys):
    monkeypatch.setenv("ORBIT_CHAVE_API", "x")
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # pytest: entrada não interativa
    assert main([]) == 1
    assert "Nada foi enviado" in capsys.readouterr().out


def test_entrada_fechada_conta_como_nao(monkeypatch, capsys):
    monkeypatch.setenv("ORBIT_CHAVE_API", "x")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    def sem_entrada(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", sem_entrada)
    assert main([]) == 1
    assert "Nada foi enviado" in capsys.readouterr().out


def test_heartbeats_demo_tem_um_silencioso_e_um_desatualizado():
    agora = datetime(2026, 11, 14, 12, tzinfo=UTC)
    eventos = [
        SimpleNamespace(id=i, **{**e, "ocorrido_em": datetime.fromisoformat(e["ocorrido_em"])})
        for i, e in enumerate(eventos_demo(agora), start=1)
    ]
    alertas = {(a.regra, a.alvo) for a in verificar_saude(eventos, agora)}
    assert alertas == {
        (REGRA_SILENCIOSA, "sensor-filial"),
        (REGRA_DESATUALIZADA, "anzol-gateway"),
    }
