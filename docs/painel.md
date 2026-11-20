# Painel web

Uma tela só, em Streamlit, para ver de relance o que o ORBIT sabe.
**O painel só lê:** chama `GET /eventos`, `GET /alertas` e `GET /alertas/{id}`
com a mesma chave das fontes. Não acessa o banco, não grava nada e não muda
regras.

## O que aparece

- **Métricas:** total de eventos, total de alertas, alertas CRÍTICOS e alvos
  distintos, em cartões com borda colorida (críticos em vermelho). Contam o
  que foi carregado com os filtros (até o limite).
- **Filtros (barra lateral):** origem, nível mínimo, alvo, "Mostrar
  heartbeats" e limite (até 200).
  Vão para a API, então valem para o banco todo, não só para a tela. O alvo é
  comparado como a API faz (sem espaços nas pontas, minúsculas) e precisa ser
  o valor exato. A origem só filtra eventos: alerta não tem origem própria.
  Heartbeats (sinal de vida das fontes, veja
  [saude_fontes.md](saude_fontes.md)) ficam ocultos por padrão. Esse filtro
  é local, depois da API, então eles ainda ocupam espaço no limite.
- **Alertas:** badges com a contagem por nível e a tabela do mais grave ao
  mais recente, com o nível colorido. Ao selecionar uma linha, aparecem o
  badge do nível e os eventos que causaram o alerta. Alertas de saúde das
  fontes (`fonte_silenciosa`, `fonte_desatualizada`) aparecem aqui também.
- **Linha do tempo:** eventos por hora (UTC) e por origem, contados por
  `ocorrido_em` (quando aconteceu), com cor fixa por origem, e a tabela dos
  eventos.

Os dados ficam em cache por 30 s; o botão **Atualizar dados** busca de novo.

## Configuração

| Variável | Padrão | Para quê |
|---|---|---|
| `ORBIT_API_URL` | `http://127.0.0.1:8000` | Onde está a API (no Docker: `http://api:8000`) |
| `ORBIT_CHAVE_API` | (obrigatória) | Chave enviada no `X-API-Key` |

## Visual

Tema escuro em [`.streamlit/config.toml`](../.streamlit/config.toml),
lido pelo Streamlit no diretório de onde ele roda (a raiz do repositório; no
Docker, `Dockerfile.painel` copia a pasta). Destaque roxo (`#7c3aed`) e ciano
no título em degradê.

| Nível | Cor | Onde |
|---|---|---|
| CRÍTICO | vermelho | célula da tabela, badge, borda do cartão de críticos |
| ALTO | laranja | célula da tabela, badge |
| MÉDIO | amarelo | célula da tabela, badge |
| BAIXO | verde | célula da tabela, badge |

- **A cor nunca está sozinha:** o nome do nível continua escrito em todo
  lugar (daltonismo, impressão em preto e branco).
- **Contraste testado** (`tests/test_painel_dados.py`, fórmula WCAG): texto
  das células de nível ≥ 4,5:1; texto do corpo ≥ 7:1; texto branco nos
  botões ≥ 4,5:1; cores do gráfico ≥ 3:1 sobre o fundo.
- **Origem tem cor própria, fora da escala dos níveis** (ciano, roxo, rosa,
  azul, cinza), fixa por origem para não mudar com o filtro. As cores de
  nível e origem moram em `painel/dados.py`; a paleta do tema repete as de
  origem (um teste garante que batem).
- **Fonte embutida** no Streamlit, sem Google Fonts: o painel não faz
  consulta externa.

## Decisões

- **Texto da API é sempre texto.** O `resumo` pode trazer dados de terceiros
  (ex.: assunto de um e-mail de phishing). Tudo que vem da API é mostrado com
  `st.dataframe` e `st.text`, que não interpretam HTML nem Markdown.
- **O único HTML é CSS fixo.** `ESTILO_FIXO` em `painel/app.py` é a única
  string com `unsafe_allow_html`: escrita no código, sem interpolar nada, e
  só mira containers com `key` criados por nós (`.st-key-…`). Badges usam
  Markdown, então só recebem textos nossos: os 4 nomes de nível conhecidos e
  contagens. Um alerta com nível fora da lista não vira badge.
  `tests/test_painel_app.py` roda a tela de verdade (Streamlit `AppTest`) com
  `<img src=x onerror=...>` no resumo, alvo e tipo e confere que ele aparece
  intacto nas tabelas e em nenhum Markdown ou HTML.
- **A chave nunca aparece.** Não é exibida, não entra em mensagens de erro nem
  em chaves de cache.
- **Erros em português, sem stack trace.** Chave ausente, chave recusada (401),
  API sem chave (503), API fora do ar ou lenta viram uma mensagem clara.
- **Lógica separada da tela.** Filtrar, ordenar, contar e agrupar por hora
  são funções puras em `painel/dados.py`, testadas em
  `tests/test_painel_dados.py`. O cliente HTTP (`painel/cliente.py`) é
  testado com uma API simulada.
- **Sem telemetria nem consulta externa:** o Docker sobe o Streamlit com
  `browser.gatherUsageStats=false` e `browser.serverAddress=localhost`.

## Limites

- **Sem login próprio, uso local.** Quem abre o painel vê tudo que a chave
  permite; por isso a porta só é publicada em `127.0.0.1:8501`.
- Métricas sobre o que foi carregado, não sobre o banco inteiro.
- Horários em UTC.
