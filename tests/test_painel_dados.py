"""Testes das funções puras do painel (sem Streamlit, sem rede)."""

from datetime import UTC, datetime

import pytest

from painel import dados


def alerta(id, nivel, criado_em, alvo="maria@x.com", **kw):
    return {"id": id, "nivel": nivel, "criado_em": criado_em, "alvo": alvo,
            "regra": "multiplas_fontes", "resumo": "r", "eventos_ids": [1, 2], **kw}


def evento(id, origem, ocorrido_em, nivel="ALTO", alvo="maria@x.com", **kw):
    return {"id": id, "origem": origem, "ocorrido_em": ocorrido_em, "nivel": nivel,
            "alvo": alvo, "tipo": "t", "resumo": "r", **kw}


# --- parâmetros e filtros -------------------------------------------------------


def test_parametros_omitem_filtros_vazios():
    assert dados.parametros(alvo="   ", origem=None, nivel_minimo=None) == {"limite": 50}


def test_parametros_normalizam_alvo_e_limitam_o_limite():
    p = dados.parametros(alvo=" Maria@X.com ", nivel_minimo="ALTO", origem="anzol", limite=999)
    assert p == {"limite": 200, "nivel_minimo": "ALTO", "alvo": "maria@x.com", "origem": "anzol"}
    assert dados.parametros(limite=0)["limite"] == 1


def test_parametros_de_alertas_nao_levam_origem():
    assert "origem" not in dados.parametros(origem="anzol", para="alertas")


def test_parametros_ignoram_valores_desconhecidos():
    assert dados.parametros(origem="inventada", nivel_minimo="ENORME") == {"limite": 50}


def test_parametros_recusam_destino_desconhecido():
    with pytest.raises(ValueError):
        dados.parametros(para="usuarios")


def test_filtrar_por_origem_nivel_e_alvo():
    eventos = [
        evento(1, "anzol", "2026-11-14T10:00:00Z", nivel="BAIXO"),
        evento(2, "anzol", "2026-11-14T10:00:00Z", nivel="CRÍTICO"),
        evento(3, "netsentinel", "2026-11-14T10:00:00Z", nivel="ALTO", alvo="joao@x.com"),
    ]
    assert [e["id"] for e in dados.filtrar(eventos, origem="anzol")] == [1, 2]
    assert [e["id"] for e in dados.filtrar(eventos, nivel_minimo="ALTO")] == [2, 3]
    assert [e["id"] for e in dados.filtrar(eventos, alvo=" JOAO@x.com")] == [3]
    assert dados.filtrar(eventos) == eventos


def test_filtrar_por_origem_nao_descarta_alertas():
    # Alerta não tem origem: o filtro de origem não se aplica a ele.
    alertas = [alerta(1, "ALTO", "2026-11-14T10:00:00Z")]
    assert dados.filtrar(alertas, origem="anzol") == alertas


# --- ordenação -------------------------------------------------------------------


def test_alertas_do_mais_grave_ao_mais_recente():
    alertas = [
        alerta(1, "ALTO", "2026-11-14T12:00:00Z"),
        alerta(2, "CRÍTICO", "2026-11-14T08:00:00Z"),
        alerta(3, "CRÍTICO", "2026-11-14T09:00:00Z"),
        alerta(4, "MÉDIO", "2026-11-14T23:00:00Z"),
    ]
    assert [a["id"] for a in dados.ordenar_alertas(alertas)] == [3, 2, 1, 4]


def test_nivel_desconhecido_fica_por_ultimo():
    alertas = [alerta(1, "???", "2026-11-14T12:00:00Z"), alerta(2, "BAIXO", None)]
    assert [a["id"] for a in dados.ordenar_alertas(alertas)] == [2, 1]


def test_eventos_do_mais_recente_ao_mais_antigo_por_ocorrido_em():
    eventos = [
        evento(1, "anzol", "2026-11-14T08:00:00Z"),
        evento(2, "anzol", "2026-11-14T12:00:00+00:00"),
        evento(3, "anzol", "2026-11-14T09:00:00-03:00"),  # 12:00 UTC também
    ]
    assert [e["id"] for e in dados.ordenar_eventos(eventos)] == [3, 2, 1]


# --- métricas -----------------------------------------------------------------------


def test_metricas_contam_totais_criticos_e_alvos_distintos():
    eventos = [
        evento(1, "anzol", "2026-11-14T10:00:00Z", alvo="maria@x.com"),
        evento(2, "netsentinel", "2026-11-14T10:00:00Z", alvo="203.0.113.5"),
    ]
    alertas = [
        alerta(1, "CRÍTICO", "2026-11-14T10:00:00Z", alvo="MARIA@x.com"),
        alerta(2, "ALTO", "2026-11-14T10:00:00Z", alvo="joao@x.com"),
    ]
    assert dados.metricas(eventos, alertas) == {
        "eventos": 2, "alertas": 2, "alertas_criticos": 1, "alvos_distintos": 3,
    }


def test_metricas_vazias():
    assert dados.metricas([], []) == {
        "eventos": 0, "alertas": 0, "alertas_criticos": 0, "alvos_distintos": 0,
    }


# --- agrupamento por hora --------------------------------------------------------------


def test_eventos_por_hora_e_origem():
    eventos = [
        evento(1, "anzol", "2026-11-14T10:05:00Z"),
        evento(2, "anzol", "2026-11-14T10:59:59Z"),
        evento(3, "netsentinel", "2026-11-14T10:30:00Z"),
        evento(4, "anzol", "2026-11-14T08:10:00-03:00"),  # 11:10 UTC
        evento(5, "anzol", "data-quebrada"),
    ]
    hora = lambda h: datetime(2026, 11, 14, h, tzinfo=UTC)  # noqa: E731
    assert dados.eventos_por_hora(eventos) == [
        {"hora": hora(10), "origem": "anzol", "eventos": 2},
        {"hora": hora(10), "origem": "netsentinel", "eventos": 1},
        {"hora": hora(11), "origem": "anzol", "eventos": 1},
    ]


def test_eventos_por_hora_vazio():
    assert dados.eventos_por_hora([]) == []


# --- linhas de tabela e cores ----------------------------------------------------------


def test_linhas_alertas_ordenadas_e_texto_preservado():
    malicioso = "<script>alert(1)</script> **negrito**"
    linhas = dados.linhas_alertas([
        alerta(1, "BAIXO", "2026-11-14T10:00:00Z"),
        alerta(2, "CRÍTICO", "2026-11-14T10:00:00Z", resumo=malicioso),
    ])
    assert [linha["id"] for linha in linhas] == [2, 1]
    assert linhas[0]["Resumo"] == malicioso  # passa intacto; a tela mostra como texto
    assert linhas[0]["Eventos"] == 2
    assert linhas[0]["Criado em (UTC)"] == datetime(2026, 11, 14, 10, tzinfo=UTC)


def test_linhas_eventos_tem_as_colunas_da_tabela():
    linha = dados.linhas_eventos([evento(1, "anzol", "2026-11-14T10:00:00Z")])[0]
    assert list(linha) == [
        "id", "Ocorrido em (UTC)", "Nível", "Origem", "Tipo", "Alvo", "Resumo",
    ]


@pytest.mark.parametrize("nivel", dados.NIVEIS)
def test_cada_nivel_tem_cor(nivel):
    assert "background-color" in dados.estilo_nivel(nivel)


def test_nivel_desconhecido_nao_ganha_estilo():
    assert dados.estilo_nivel("<b>x</b>") == ""
    assert dados.estilo_nivel(None) == ""
