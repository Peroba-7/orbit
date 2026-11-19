# Painel web (etapa 3)

Uma tela só, em Streamlit, para ver de relance o que o ORBIT sabe.
**O painel só lê:** chama `GET /eventos`, `GET /alertas` e `GET /alertas/{id}`
com a mesma chave das fontes. Não acessa o banco, não grava nada e não muda
regras.

## O que aparece

- **Métricas:** total de eventos, total de alertas, alertas CRÍTICOS e alvos
  distintos. Contam o que foi carregado com os filtros (até o limite).
- **Filtros (barra lateral):** origem, nível mínimo, alvo e limite (até 200).
  Vão para a API, então valem para o banco todo, não só para a tela. O alvo é
  comparado como a API faz (sem espaços nas pontas, minúsculas) e precisa ser
  o valor exato. A origem só filtra eventos: alerta não tem origem própria.
- **Alertas:** do mais grave ao mais recente, com o nível colorido. Ao
  selecionar uma linha, aparecem os eventos que causaram o alerta.
- **Linha do tempo:** eventos por hora (UTC) e por origem, contados por
  `ocorrido_em` (quando aconteceu), e a tabela dos eventos.

Os dados ficam em cache por 30 s; o botão **Atualizar dados** busca de novo.

## Configuração

| Variável | Padrão | Para quê |
|---|---|---|
| `ORBIT_API_URL` | `http://127.0.0.1:8000` | Onde está a API (no Docker: `http://api:8000`) |
| `ORBIT_CHAVE_API` | (obrigatória) | Chave enviada no `X-API-Key` |

## Decisões

- **Texto da API é sempre texto.** O `resumo` pode trazer dados de terceiros
  (ex.: assunto de um e-mail de phishing). Tudo que vem da API é mostrado com
  `st.dataframe` e `st.text`, que não interpretam HTML nem Markdown.
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
