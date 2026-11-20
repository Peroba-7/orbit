"""A tela do painel rodando de verdade (Streamlit AppTest), com a API simulada.

Foco: texto vindo da API continua texto puro mesmo com o visual novo. O único
HTML liberado na página é o CSS fixo (ESTILO_FIXO); badges e Markdown só
levam textos nossos.
"""

from pathlib import Path
from unittest import mock

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "painel" / "app.py")
PAYLOAD = '<img src=x onerror="alert(1)">'


def _evento(id, **kw):
    return {"id": id, "origem": "anzol", "tipo": "phishing_detectado",
            "alvo": "maria@exemplo.com.br", "nivel": "ALTO", "resumo": "ok",
            "ocorrido_em": "2026-11-19T10:00:00Z", "recebido_em": "2026-11-19T10:00:00Z",
            "detalhes": {}, **kw}


def _alerta(id, **kw):
    return {"id": id, "regra": "multiplas_fontes", "nivel": "CRÍTICO",
            "alvo": "maria@exemplo.com.br", "resumo": "ok", "eventos_ids": [1, 2],
            "criado_em": "2026-11-19T10:00:00Z", **kw}


EVENTOS = [
    _evento(1, resumo=PAYLOAD),
    _evento(2, alvo=PAYLOAD, tipo=PAYLOAD, origem="netsentinel"),
]
ALERTAS = [
    _alerta(1, resumo=PAYLOAD),
    _alerta(2, nivel=PAYLOAD, alvo=PAYLOAD),  # nível inválido: API não manda, painel aguenta
]


@pytest.fixture
def tela(monkeypatch):
    monkeypatch.setenv("ORBIT_CHAVE_API", "chave-de-teste")
    st.cache_data.clear()
    with (
        mock.patch("painel.cliente.ClienteOrbit.listar_eventos", return_value=EVENTOS),
        mock.patch("painel.cliente.ClienteOrbit.listar_alertas", return_value=ALERTAS),
    ):
        at = AppTest.from_file(APP, default_timeout=30).run()
        yield at
    st.cache_data.clear()


def _textos_interpretados(at):
    """Tudo que o Streamlit interpreta como Markdown/HTML na página (badges inclusive)."""
    return [str(e.value) for e in [*at.markdown, *at.caption, *at.title, *at.subheader]]


def _badges(at):
    """st.badge vira Markdown ':cor-badge[rótulo]'; devolve (cor, rótulo)."""
    achados = []
    for m in at.markdown:
        valor = str(m.value)
        if valor.startswith(":") and "-badge[" in valor and valor.endswith("]"):
            cor, rotulo = valor[1:-1].split("-badge[", 1)
            achados.append((cor, rotulo))
    return achados


def test_painel_renderiza_sem_erro(tela):
    assert not tela.exception
    assert [t.value for t in tela.title] == ["ORBIT"]


def test_unico_html_liberado_e_o_css_fixo(tela):
    from painel.app import ESTILO_FIXO

    com_html = [m.value for m in tela.markdown if getattr(m.proto, "allow_html", False)]
    assert com_html == [ESTILO_FIXO.strip()]
    assert "onerror" not in ESTILO_FIXO and "{{" not in ESTILO_FIXO


def test_img_onerror_nao_entra_em_markdown_badge_nem_html(tela):
    for texto in _textos_interpretados(tela):
        assert "onerror" not in texto, texto
        assert "<img" not in texto, texto


def test_img_onerror_aparece_intacto_como_texto_nas_tabelas(tela):
    celulas = set()
    for tabela in tela.dataframe:
        df = tabela.value
        celulas.update(str(v) for v in df.to_numpy().ravel())
    # Resumo, alvo e tipo maliciosos estão lá, exatamente como vieram.
    assert PAYLOAD in celulas


def test_badges_de_nivel_so_com_nomes_fixos_e_cor_da_escala(tela):
    from painel import dados

    # Um badge por nível conhecido, com contagem; o alerta de nível inválido não conta.
    assert _badges(tela) == [
        ("red", "CRÍTICO · 1"), ("orange", "ALTO · 0"),
        ("yellow", "MÉDIO · 0"), ("green", "BAIXO · 0"),
    ]
    for cor, rotulo in _badges(tela):
        nivel = rotulo.split(" · ")[0]
        assert dados.BADGE_NIVEL[nivel] == cor
