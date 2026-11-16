# Motor de correlação (etapa 2)

Um evento sozinho conta pouco. Um phishing para a Maria pode não ter dado em
nada; uma falha de login dela pode ser só a senha digitada errado. **Os dois
juntos, perto no tempo, sugerem que a senha foi roubada e alguém está testando.**
O motor de correlação procura exatamente esse tipo de combinação.

## Princípios

- **Regras fixas, sem IA.** Cada alerta diz qual regra disparou e quais eventos
  o causaram (`GET /alertas/{id}`). Dá para conferir à mão.
- **Só o mesmo alvo.** Eventos de alvos diferentes nunca se misturam. O alvo é
  normalizado (sem espaços nas pontas, minúsculas) ao gravar e ao filtrar:
  `"Maria@X.com "` e `"maria@x.com"` são o mesmo alvo.
- **O tempo é o do fato.** As janelas contam por `ocorrido_em` (quando
  aconteceu), não por `recebido_em` (quando chegou). Uma fonte que envia com
  atraso ainda correlaciona corretamente.
- **O nível só sobe.** Todo alerta tem nível maior ou igual ao maior nível dos
  seus eventos. Um evento fraco que chega depois não rebaixa nada: alertas
  gravados nunca são alterados.
- **Sem duplicatas.** Mesma regra + mesmo alvo + mesmo conjunto de eventos =
  mesmo alerta, gravado uma vez só (garantido por restrição única no banco).

## A janela

Padrão: **24 horas**, configurável em `ORBIT_JANELA_HORAS` (número positivo,
aceita fração como `0.5`). Valor inválido impede a API de subir, para não
rodar com o motor calado ou disparando à toa sem ninguém perceber.

Por que 24 h: cobre o caso típico "phishing de manhã, tentativa de login à
tarde ou no dia seguinte cedo" sem juntar coisas de semanas diferentes.

Vale para `phishing_mais_login_falho` e `multiplas_fontes`. A rajada tem
janela própria e fixa de 1 h (ver abaixo).

## As regras

| Regra | Dispara quando | Nível |
|---|---|---|
| `phishing_mais_login_falho` | Anzol: `tipo` em `TIPOS_PHISHING` **e** NetSentinel: `tipo` em `TIPOS_LOGIN_FALHO`, até a janela de diferença, em qualquer ordem | CRÍTICO |
| `rajada_de_alertas` | 3 ou mais eventos ALTO ou CRÍTICO em até 1 h | CRÍTICO |
| `multiplas_fontes` | 2 ou mais origens diferentes dentro da janela | um acima do maior evento (máx. CRÍTICO) |
| (evento isolado) | nada combina | sem alerta |

### `phishing_mais_login_falho`

O par clássico de roubo de credencial. Exige **origens diferentes de
propósito**: o Anzol dizendo "login falho" não é o NetSentinel vendo login
falho; a força da regra vem de duas fontes independentes concordarem.
Tipos considerados (comparados em minúsculas), editáveis em
[app/correlacao.py](../app/correlacao.py):

```python
TIPOS_PHISHING = {"phishing_detectado"}
TIPOS_LOGIN_FALHO = {"login_falho", "brute_force"}
```

> Os tipos reais emitidos pelo NetSentinel ainda precisam ser conferidos.

### `rajada_de_alertas`

Muitos eventos graves em pouco tempo indicam ataque em andamento ou
insistente, mesmo vindo de uma só fonte. A janela é curta (1 h) porque a
ideia é pegar a *rajada*: três eventos ALTO espalhados num dia são outra
história. BAIXO e MÉDIO não contam.

### `multiplas_fontes`

Quando sensores diferentes (rede, e-mail, honeypot...) olham para o mesmo
alvo na mesma janela, a chance de ser coincidência cai. Por isso o alerta
fica **um nível acima** do evento mais grave do grupo: BAIXO→MÉDIO,
MÉDIO→ALTO, ALTO→CRÍTICO, CRÍTICO→CRÍTICO.

Pode disparar junto com `phishing_mais_login_falho` (que também envolve duas
fontes): são duas leituras diferentes do mesmo grupo e as duas ficam
registradas.

## Como os eventos de cada alerta são escolhidos

Cada evento serve de **âncora** e a regra olha só para trás a partir dele:
eventos do mesmo alvo com `ocorrido_em` entre `âncora − janela` e `âncora`.
Isso torna o conjunto de cada alerta determinístico, e é o que permite
reconhecer duplicatas.

Quando um evento chega (`POST /eventos`), o ORBIT:

1. grava o evento;
2. busca os eventos do mesmo alvo num raio de uma janela antes e depois dele;
3. roda a função pura `correlacionar()` (sem banco, fácil de testar);
4. grava só os alertas que **incluem o evento novo** e que ainda não existem.

Consequência: se o grupo cresce (um terceiro evento chega na janela), nasce
um **novo** alerta com o conjunto maior; o anterior fica como estava, como
registro histórico.

## Consultar

```bash
curl -H "X-API-Key: minha-chave" "http://127.0.0.1:8000/alertas?nivel_minimo=ALTO&alvo=maria@empresa.com.br"
curl -H "X-API-Key: minha-chave" "http://127.0.0.1:8000/alertas/1"   # inclui os eventos
```

Filtros de `GET /alertas`: `nivel_minimo`, `alvo`, `limite` (1 a 200,
padrão 50). Ordem: do mais recente para o mais antigo.

## Limites conhecidos

- Grupos que crescem geram um alerta novo a cada evento que entra na janela;
  pode ficar ruidoso para um alvo muito ativo. Agrupar/atualizar alertas fica
  para uma próxima etapa.
- Um evento que chega muito atrasado pode gerar vários alertas de uma vez
  (ele muda a janela de todos os eventos posteriores).
- Não há limite de quantos eventos de um alvo entram numa correlação.
- Eventos gravados na etapa 1 com alvo em maiúsculas não foram migrados.
