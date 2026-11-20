"""Painel do ORBIT (etapa 3): tela única, somente leitura.

Só chama GET /eventos, GET /alertas e GET /alertas/{id}. Não grava nada e não
mexe nas regras. Rodar a partir da raiz do repositório:

    python -m streamlit run painel/app.py

Segurança: todo texto vindo da API (resumo, alvo, tipo...) é exibido como
TEXTO, só com st.dataframe e st.text, que não interpretam HTML nem Markdown.
O campo resumo pode conter dados de terceiros (ex.: assunto de e-mail).

Visual: tema escuro em .streamlit/config.toml. O único HTML da página é o CSS
fixo de ESTILO_FIXO (escrito aqui, nunca com dado da API dentro). Badges só
recebem textos nossos: os 4 nomes de nível conhecidos e contagens.
"""

from typing import Any

import altair as alt
import pandas as pd
import streamlit as st

from painel import dados
from painel.cliente import ClienteOrbit, ErroDaApi, url_da_api

st.set_page_config(page_title="ORBIT · painel", page_icon=":material/radar:", layout="wide")

CACHE_SEGUNDOS = 30
FORMATO_DATA = "DD/MM/YYYY HH:mm"


@st.cache_data(ttl=CACHE_SEGUNDOS, show_spinner=False)
def carregar_lista(recurso: str, params: dict[str, Any]) -> list[dict[str, Any]]:
    # O cliente é criado aqui dentro: a chave nunca vira argumento de cache.
    cliente = ClienteOrbit()
    if recurso == "eventos":
        return cliente.listar_eventos(params)
    return cliente.listar_alertas(params)


@st.cache_data(ttl=CACHE_SEGUNDOS, show_spinner=False)
def carregar_alerta(alerta_id: int) -> dict[str, Any]:
    return ClienteOrbit().obter_alerta(alerta_id)


def tabela_colorida(linhas: list[dict[str, Any]]):
    """DataFrame com a coluna Nível colorida (cores fixas, só para os 4 níveis)."""
    df = pd.DataFrame(linhas)
    return df.style.map(dados.estilo_nivel, subset=["Nível"])


COLUNAS_DATA = {
    nome: st.column_config.DatetimeColumn(nome, format=FORMATO_DATA, timezone="UTC")
    for nome in ("Ocorrido em (UTC)", "Criado em (UTC)")
}
COLUNA_ID = {"id": st.column_config.NumberColumn("id", width="small", format="%d")}
COLUNA_RESUMO = {"Resumo": st.column_config.TextColumn("Resumo", width="large")}
CONFIG_COLUNAS = {**COLUNAS_DATA, **COLUNA_ID, **COLUNA_RESUMO}

# Cartões de métrica: (chave do container, rótulo, chave em dados.metricas, ícone).
# A cor da borda de cada um está em ESTILO_FIXO (críticos em vermelho).
CARTOES = [
    ("metrica_eventos", "Eventos", "eventos", ":material/sensors:"),
    ("metrica_alertas", "Alertas", "alertas", ":material/notifications_active:"),
    ("metrica_criticos", "Alertas críticos", "alertas_criticos", ":material/crisis_alert:"),
    ("metrica_alvos", "Alvos distintos", "alvos_distintos", ":material/my_location:"),
]

# CSS FIXO. Não interpole nada aqui: é a única string passada com
# unsafe_allow_html, e por isso nunca pode conter dado vindo da API.
# Só mira containers com `key` criados por nós (classe .st-key-<key>).
ESTILO_FIXO = """
<style>
.st-key-cabecalho h1, .st-key-cabecalho h1 * {
  background: linear-gradient(90deg, #22d3ee 0%, #a78bfa 55%, #f472b6 100%);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  letter-spacing: 0.12em;
  font-size: 3.25rem;
  line-height: 1.1;
}
.st-key-metrica_eventos, .st-key-metrica_alertas,
.st-key-metrica_criticos, .st-key-metrica_alvos {
  background: #141b2d;
  border: 1px solid #2a3350;
  border-left: 5px solid #22d3ee;
  border-radius: 10px;
  padding: 0.85rem 1rem;
}
.st-key-metrica_alertas { border-left-color: #a78bfa; }
.st-key-metrica_criticos { border-left-color: #ef4444; border-color: #7f1d1d; }
.st-key-metrica_alvos { border-left-color: #60a5fa; }
</style>
"""


# --- Barra lateral: filtros ----------------------------------------------------------

with st.sidebar:
    st.header("Filtros")
    origem = st.selectbox(
        "Origem", dados.ORIGENS, index=None, placeholder="Todas", key="filtro_origem",
        help="Vale só para eventos: alertas não têm origem própria.",
    )
    nivel_minimo = st.segmented_control("Nível mínimo", dados.NIVEIS, key="filtro_nivel")
    alvo = st.text_input(
        "Alvo", max_chars=255, placeholder="maria@exemplo.com.br", key="filtro_alvo",
        help="Valor exato (maiúsculas e espaços nas pontas não importam).",
    )
    mostrar_heartbeats = st.toggle(
        "Mostrar heartbeats", value=False, key="filtro_heartbeats",
        help="Sinais de vida que as fontes enviam para provar que estão no ar. "
        "Não são eventos de segurança, por isso ficam ocultos por padrão.",
    )
    limite = st.slider(
        "Limite por lista", 10, dados.LIMITE_MAXIMO, 100, step=10, key="filtro_limite"
    )
    if st.button("Atualizar dados", icon=":material/refresh:", width="stretch"):
        st.cache_data.clear()
    st.caption(f"Dados em cache por {CACHE_SEGUNDOS} s. Somente leitura.")
    st.text(f"API: {url_da_api()}")

filtros = {"origem": origem, "nivel_minimo": nivel_minimo, "alvo": alvo}


# --- Cabeçalho ---------------------------------------------------------------------------

st.markdown(ESTILO_FIXO, unsafe_allow_html=True)  # só CSS fixo, nenhum dado

with st.container(key="cabecalho"):
    st.title("ORBIT", anchor=False)
    st.caption(
        "Mini-SOC · eventos e alertas de segurança correlacionados por alvo · somente leitura"
    )


# --- Dados -----------------------------------------------------------------------------

try:
    eventos = carregar_lista("eventos", dados.parametros(**filtros, limite=limite))
    alertas = carregar_lista(
        "alertas", dados.parametros(**filtros, limite=limite, para="alertas")
    )
except ErroDaApi as erro:
    st.error(str(erro), title="Não foi possível carregar os dados", icon=":material/error:")
    st.stop()

# Rede de segurança: aplica os mesmos filtros sobre a resposta.
eventos = dados.filtrar(eventos, **filtros)
if not mostrar_heartbeats:
    eventos = dados.sem_heartbeats(eventos)
alertas = dados.filtrar(alertas, **filtros)


# --- Métricas ---------------------------------------------------------------------------

numeros = dados.metricas(eventos, alertas)
with st.container(horizontal=True):
    for chave, rotulo, campo, icone in CARTOES:
        with st.container(key=chave):
            st.metric(rotulo, numeros[campo], icon=icone)
st.caption(
    f"Contagens sobre o que foi carregado com os filtros (até {limite} por lista)."
    + ("" if mostrar_heartbeats else " Heartbeats ocultos.")
)


# --- Alertas -----------------------------------------------------------------------------

st.subheader("Alertas", anchor=False)
with st.container(horizontal=True, key="badges_niveis"):
    # Rótulo = nome de nível da lista fixa + número: nada vindo da API.
    for nivel, quantidade in dados.contagem_por_nivel(alertas):
        st.badge(f"{nivel} · {quantidade}", color=dados.BADGE_NIVEL[nivel])
if not alertas:
    st.info("Nenhum alerta com esses filtros.", icon=":material/check_circle:")
else:
    linhas = dados.linhas_alertas(alertas)
    selecao = st.dataframe(
        tabela_colorida(linhas),
        hide_index=True,
        column_config=CONFIG_COLUNAS,
        on_select="rerun",
        selection_mode="single-row",
        key="tabela_alertas",
        alt="Alertas, do mais grave ao mais recente",
    )
    st.caption("Selecione um alerta para ver os eventos que o causaram.")

    escolhidas = selecao.selection.rows
    if escolhidas:
        alerta_id = int(linhas[escolhidas[0]]["id"])
        with st.container(border=True):
            try:
                detalhe = carregar_alerta(alerta_id)
            except ErroDaApi as erro:
                st.error(str(erro), title="Não foi possível abrir o alerta")
            else:
                nivel = detalhe.get("nivel")
                if nivel in dados.BADGE_NIVEL:
                    # Só um dos 4 nomes fixos vira badge (Markdown); outro valor, não.
                    st.badge(nivel, color=dados.BADGE_NIVEL[nivel])
                st.text(
                    f"Alerta #{detalhe.get('id')} · {detalhe.get('nivel')} · "
                    f"regra {detalhe.get('regra')} · alvo {detalhe.get('alvo')}"
                )
                st.text(str(detalhe.get("resumo") or ""))
                eventos_do_alerta = detalhe.get("eventos") or []
                st.dataframe(
                    tabela_colorida(dados.linhas_eventos(eventos_do_alerta)),
                    hide_index=True,
                    column_config=CONFIG_COLUNAS,
                    alt="Eventos que causaram o alerta selecionado",
                )


# --- Linha do tempo ---------------------------------------------------------------------------

st.subheader("Linha do tempo", anchor=False)
if not eventos:
    st.info("Nenhum evento com esses filtros.", icon=":material/info:")
else:
    por_hora = pd.DataFrame(dados.eventos_por_hora(eventos))
    if not por_hora.empty:
        grafico = (
            alt.Chart(por_hora)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("hora:T", timeUnit="utcyearmonthdatehours", title="Hora (UTC)"),
                y=alt.Y("eventos:Q", stack=True, title="Eventos"),
                color=alt.Color(
                    "origem:N",
                    title="Origem",
                    # Cor fixa por origem: a mesma em qualquer filtro.
                    scale=alt.Scale(
                        domain=list(dados.CORES_ORIGEM),
                        range=list(dados.CORES_ORIGEM.values()),
                    ),
                ),
                tooltip=[
                    alt.Tooltip("hora:T", timeUnit="utcyearmonthdatehours", title="Hora (UTC)"),
                    alt.Tooltip("origem:N", title="Origem"),
                    alt.Tooltip("eventos:Q", title="Eventos"),
                ],
            )
            .properties(height=280)
        )
        st.altair_chart(grafico, alt="Eventos por hora, empilhados por origem")
    st.dataframe(
        tabela_colorida(dados.linhas_eventos(eventos)),
        hide_index=True,
        column_config=CONFIG_COLUNAS,
        alt="Eventos, do mais recente ao mais antigo",
    )
