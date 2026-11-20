# Saúde das fontes (etapa 4)

Um ORBIT sem alertas pode ser um dia tranquilo **ou um sensor que caiu sem
ninguém ver**. Do ponto de vista do painel, os dois parecem iguais. Esta regra
separa os dois casos: cada fonte manda, de tempos em tempos, um evento de
sinal de vida (`heartbeat`), e o ORBIT avisa quando esse sinal some ou quando
a fonte está rodando com regras velhas.

## O heartbeat

É um evento comum (mesmo molde de [evento.md](evento.md)), com `tipo`
`heartbeat`. O `alvo` identifica o sensor (nome do host, por exemplo) e
`detalhes.versao_regras` diz a data da versão das regras de detecção que ele
está usando, no formato `AAAA-MM-DD`.

```json
{
  "origem": "netsentinel",
  "tipo": "heartbeat",
  "alvo": "sensor-sede",
  "nivel": "BAIXO",
  "resumo": "Sinal de vida do sensor.",
  "ocorrido_em": "2026-11-19T12:00:00Z",
  "detalhes": { "versao_regras": "2026-11-18" }
}
```

## As regras

O último heartbeat de cada par **(origem, alvo)** é avaliado (alvo normalizado
como no resto do ORBIT: sem espaços nas pontas, minúsculas). Heartbeats mais
antigos do mesmo par não contam.

| Regra | Dispara quando | Nível |
|---|---|---|
| `fonte_silenciosa` | último heartbeat **mais antigo** que o limite de silêncio | ALTO |
| `fonte_desatualizada` | heartbeat recente, mas `versao_regras` **mais velha** que o limite de desatualização | MÉDIO |
| `fonte_desatualizada` (versão desconhecida) | heartbeat recente, sem `versao_regras` ou com data inválida | MÉDIO |
| (nada) | heartbeat recente e regras em dia, ou nenhum heartbeat | sem alerta |

- **Exatamente no limite ainda está ok.** Silêncio de 3 h com limite de 3 h não
  alerta; 3 h e 1 s alerta. Versão de 7 dias com limite de 7 não alerta; 8
  dias alerta.
- **Silenciosa tem prioridade.** Se a fonte está calada, não adianta avaliar a
  versão das regras: sai só o alerta de silêncio.
- **Data inválida não quebra nada.** Faltando `versao_regras`, ou vindo algo
  como `"ontem"`, `"18/11/2026"`, `"20261118"`, `"2026-02-30"` ou um número, o
  alerta diz que a versão é desconhecida. Não dá para garantir que as regras
  estão em dia, e isso já é um problema.
- **Só a falta de heartbeat gera alerta.** Eventos comuns (phishing, login
  falho...) não dizem nada sobre a saúde da fonte e são ignorados. Uma fonte
  que **nunca** mandou heartbeat também não gera alerta: o ORBIT não tem como
  saber que ela existe.
- **Sem duplicatas.** Mesma chave dos outros alertas: (regra, alvo, assinatura
  dos eventos). Cada alerta aponta para o heartbeat que o causou.
- **Por que ALTO e MÉDIO.** Fonte calada é ponto cego total: um ataque àquele
  alvo não aparece em lugar nenhum. Regras velhas ainda detectam o conhecido,
  só deixam passar o novo.

## O tempo

A função é pura: recebe `agora` de fora em vez de ler o relógio. Isso torna os
testes exatos e permite reavaliar o passado.

- `agora` precisa ter fuso; sem fuso, dá erro (`ValueError`).
- O silêncio é a diferença entre `agora` e o `ocorrido_em` do último
  heartbeat, já em UTC. O mesmo instante em fusos diferentes dá o mesmo
  resultado. Heartbeat sem fuso é tratado como UTC (é como o banco grava).
- A idade da versão conta **dias de calendário pela data de `agora` em UTC**.
  Às 22:00 em Brasília (UTC−3) já é o dia seguinte em UTC.
- Heartbeat ou versão "no futuro" (relógio do sensor adiantado) não alerta.

## Limites (configuração)

| Variável | Padrão | Aceita |
|---|---|---|
| `ORBIT_SILENCIO_HORAS` | 3 | número positivo, com fração (ex.: `0.5`) |
| `ORBIT_DESATUALIZACAO_DIAS` | 7 | inteiro positivo |

Lidos por `silencio_horas()` e `desatualizacao_dias()` em
[app/config.py](../app/config.py). **Valor inválido cai no padrão**, com aviso
no log. É o contrário de `ORBIT_JANELA_HORAS`, que impede a API de subir:
aqui um erro só muda quando o aviso aparece, e derrubar a API por isso
deixaria o ORBIT inteiro cego.

Escolha do padrão: 3 h tolera um sensor que manda sinal a cada hora e perde
um ou dois envios, mas avisa no mesmo turno de trabalho. 7 dias é uma semana
de atraso em atualização de regras.

## Relação com o resto do ORBIT

- **Heartbeats ficam fora da correlação.** O motor de
  [correlacao.md](correlacao.md) ignora o tipo `heartbeat` (`TIPOS_IGNORADOS`
  em `app/correlacao.py`). Sem isso, dois sensores mandando sinal de vida
  para o mesmo alvo disparariam `multiplas_fontes`.
- **No painel, heartbeats ficam ocultos por padrão** (opção "Mostrar
  heartbeats" na barra lateral). Veja [painel.md](painel.md).
- `scripts/popular_demo.py` envia heartbeats fictícios: `sensor-sede` (ok),
  `sensor-filial` (silencioso) e `anzol-gateway` (desatualizado). Os alertas
  de saúde aparecem até um ciclo do agendador depois (5 min, por padrão).

## Execução automática (etapa 4, parte 2)

A regra roda sozinha, dentro da própria API. Na subida (lifespan do FastAPI,
em [app/main.py](../app/main.py)) nasce uma tarefa asyncio
([app/agendador.py](../app/agendador.py)) que repete:

1. espera `ORBIT_VERIFICACAO_MINUTOS` (padrão 5);
2. busca os heartbeats no banco, chama `verificar_saude(eventos, agora)` com a
   hora atual em UTC e grava só os alertas novos
   (`verificar_saude_e_gravar` em [app/alertas.py](../app/alertas.py)).

Os alertas gravados são alertas comuns: aparecem em `GET /alertas`,
`GET /alertas/{id}` (com o heartbeat que os causou) e no painel, com regra
`fonte_silenciosa` ou `fonte_desatualizada`.

| Variável | Padrão | Aceita |
|---|---|---|
| `ORBIT_VERIFICACAO_MINUTOS` | 5 | número ≥ 0, com fração; **0 desliga** |

Inválido (negativo, texto, infinito) cai no padrão com aviso no log. As três
variáveis da saúde das fontes (`ORBIT_SILENCIO_HORAS`,
`ORBIT_DESATUALIZACAO_DIAS` e `ORBIT_VERIFICACAO_MINUTOS`) são lidas **uma vez,
na subida**, para um valor inválido gerar um aviso só e não um por ciclo.
Mudar exige reiniciar a API.

### Decisões

- **Uma falha não derruba a API.** Qualquer erro numa verificação (banco fora
  do ar, dado estranho) vai para o log com o traceback e a próxima tentativa
  acontece no ciclo seguinte. A API continua recebendo eventos.
- **Primeiro ciclo só depois de um intervalo.** Se a API ficou fora do ar por
  horas, as fontes não conseguiram mandar heartbeat nesse tempo. Verificar na
  subida transformaria toda reinicialização numa chuva de alertas de
  silêncio; esperando um intervalo, quem está vivo tem tempo de se apresentar.
- **Roda numa thread.** O banco é síncrono; a consulta não trava as
  requisições.
- **Desligamento limpo.** Ao desligar, a tarefa é cancelada e aguardada. Se
  uma verificação estiver no meio, a thread dela termina sozinha (threads não
  são interrompidas); o que ela gravar segue o mesmo dedupe.
- **Não varre o histórico inteiro.** A cada ciclo, o banco devolve só o último
  heartbeat de cada (origem, alvo) e, para cada um, o primeiro heartbeat com a
  mesma versão das regras (veja abaixo). Uma consulta extra por fonte.

### Dedupe: um alerta por problema, não por ciclo

O dedupe é o mesmo das outras regras: (regra, alvo, assinatura dos eventos),
com restrição única no banco. O que define a assinatura é **qual heartbeat o
alerta cita**:

- **Silenciosa:** cita o último heartbeat. Enquanto a fonte está calada, ele
  não muda, então todo ciclo propõe o mesmo alerta e nada se repete. Se a
  fonte volta e cala de novo, o último heartbeat é outro: alerta novo.
- **Desatualizada:** cita o **primeiro** heartbeat recebido com a mesma
  `versao_regras` do último. Se citasse o último, um sensor desatualizado que
  manda sinal a cada 5 min geraria um alerta MÉDIO a cada 5 min (~288 por
  dia). Assim sai **um alerta por fonte e versão**; se o sensor troca para
  outra versão ainda velha, sai outro. Versão ausente conta como uma versão
  ("desconhecida"). Em formato estranho (número, lista), cita o último.

### Mais de uma instância da API

Cada instância (vários workers do uvicorn, várias réplicas) roda seu próprio
agendador. **Não há duplicata de alerta**: o dedupe consulta o banco antes de
gravar e, numa corrida entre instâncias, a restrição única do banco recusa a
cópia (o mesmo caminho já usado pelo `POST /eventos`). O custo é só trabalho
repetido: N instâncias fazem N verificações por intervalo. Para muitas
instâncias, desligue nas extras com `ORBIT_VERIFICACAO_MINUTOS=0` e deixe o
agendador ligado em uma só. O Docker Compose do projeto sobe uma instância
com um worker.

### Uso direto

```python
from datetime import UTC, datetime
from app.alertas import verificar_saude_e_gravar
from app.banco import FabricaDeSessao

with FabricaDeSessao() as sessao:
    novos = verificar_saude_e_gravar(
        sessao, datetime.now(UTC), limite_silencio_horas=3, limite_desatualizacao_dias=7
    )
```

`agora` vem de fora: os testes passam uma hora fixa, sem relógio nem sleep.

## Limites conhecidos

- **Alertas não se fecham sozinhos.** Uma fonte que volta a falar não
  "resolve" o alerta de silêncio; ele fica como registro. Ainda não existe
  estado aberto/resolvido para alertas.
- O resumo do alerta é escrito na hora em que ele nasce ("sem sinal há 3 h
  5 min") e não é atualizado depois.
- Uma fonte desligada de propósito continua "silenciosa" para sempre (um
  alerta só, mas ele existe): ainda não há como descadastrar uma fonte.
- Só se vê quem já mandou heartbeat alguma vez; não existe lista de fontes
  esperadas.
- A versão das regras é só uma data informada pela própria fonte, sem
  verificação.
- Sem índice por `tipo`: achar os heartbeats percorre a tabela de eventos a
  cada ciclo. Para bancos grandes, falta um índice (com migração, que o
  projeto ainda não tem).
- A busca pela versão usa consulta em JSON (`detalhes->>'versao_regras'`).
  Testada no SQLite; no PostgreSQL é o operador padrão para o tipo `JSON`,
  mas ainda sem teste automatizado contra um PostgreSQL real.
- Configuração lida só na subida; mudar exige reiniciar a API.
