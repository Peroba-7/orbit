# O evento normalizado

Toda fonte do ORBIT (NetSentinel, Anzol, honeypot, scanner de segredos, logs)
envia ao ORBIT **o mesmo molde**. Sem isso, não dá para comparar sinais de
fontes diferentes e a correlação (etapa 2) não funciona.

| Campo | Quem preenche | Descrição |
|---|---|---|
| `origem` | fonte | `netsentinel`, `anzol`, `honeypot`, `scanner_segredos` ou `logs` |
| `tipo` | fonte | O que aconteceu, em poucas palavras (ex.: `phishing_detectado`) |
| `alvo` | fonte | Quem ou o que foi alvo: usuário, e-mail, IP ou domínio |
| `nivel` | fonte | `BAIXO`, `MÉDIO`, `ALTO` ou `CRÍTICO` (mesma escala do Anzol) |
| `resumo` | fonte | Frase curta (até 500 caracteres) |
| `ocorrido_em` | fonte | Quando o fato aconteceu, com fuso. Se omitido, vale "agora" |
| `detalhes` | fonte | Dados específicos da fonte (JSON até 8 KB) |
| `id` | ORBIT | Número do evento |
| `recebido_em` | ORBIT | Quando o ORBIT recebeu |

## Decisões

- **`alvo` é o elo da correlação.** "Login suspeito + phishing para o mesmo
  usuário" só é detectável porque as duas fontes escrevem o usuário no `alvo`.
  O ORBIT normaliza o alvo (sem espaços nas pontas, minúsculas) ao gravar e ao
  filtrar; veja [correlacao.md](correlacao.md). E-mail vs. nome de usuário
  ainda não são unificados: a fonte deve mandar sempre a mesma forma.
- **`ocorrido_em` exige fuso.** Fontes em horários diferentes quebrariam a
  linha do tempo. Tudo é convertido para UTC.
- **A fonte não escolhe `id` nem `recebido_em`.** Campos extras são recusados.
- **`detalhes` é livre, mas limitado.** Cada fonte põe o que quiser lá (ex.: os
  sinais do Anzol), sem o ORBIT precisar conhecer todos. O limite de tamanho
  evita que alguém entupa o banco.
- **O ORBIT guarda dados mínimos.** Para e-mails, mande indícios e níveis, nunca
  o conteúdo da mensagem (mesmo princípio do Anzol, pensando em LGPD).

## Exemplo

```json
{
  "origem": "anzol",
  "tipo": "phishing_detectado",
  "alvo": "maria@empresa.com.br",
  "nivel": "CRÍTICO",
  "resumo": "E-mail com DMARC falhando e domínio parecido com marca.",
  "ocorrido_em": "2026-11-14T10:00:00Z",
  "detalhes": { "sinais": ["dmarc_falhou", "dominio_parecido_com_marca"] }
}
```
