# Saúde das fontes (etapa 4, parte 1)

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
  `sensor-filial` (silencioso) e `anzol-gateway` (desatualizado).

## Uso

```python
from datetime import UTC, datetime
from app.config import desatualizacao_dias, silencio_horas
from app.saude_fontes import verificar_saude

alertas = verificar_saude(
    eventos, datetime.now(UTC),
    limite_silencio_horas=silencio_horas(),
    limite_desatualizacao_dias=desatualizacao_dias(),
)
```

Devolve `AlertaProposto` (o mesmo tipo do motor de correlação), pronto para
ser gravado como os outros alertas.

## Limites conhecidos

- **A regra ainda não roda sozinha.** Nesta parte só existem a função, a
  configuração e os testes. Nada chama `verificar_saude` periodicamente e os
  alertas de saúde ainda não são gravados no banco nem aparecem em
  `GET /alertas`. Isso fica para a próxima parte. Detalhe: uma fonte
  silenciosa não manda evento, então a verificação não pode depender do
  `POST /eventos`; precisa de um agendamento.
- Uma fonte desligada de propósito continua "silenciosa" para sempre: ainda
  não há como descadastrar uma fonte.
- Só se vê quem já mandou heartbeat alguma vez; não existe lista de fontes
  esperadas.
- A versão das regras é só uma data informada pela própria fonte, sem
  verificação.
