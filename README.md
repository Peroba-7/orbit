# ORBIT

Mini-SOC (centro de operações de segurança) próprio: recebe sinais de várias
fontes de segurança, guarda num formato único e, nas próximas etapas,
correlaciona e mostra o risco numa tela só.

> **Estado: etapa 1 de 5 (núcleo e banco).** Ainda não correlaciona nem tem painel.

## Roadmap

1. **Núcleo e banco**: API que recebe e lista eventos (NetSentinel e Anzol). ← aqui
2. Motor de correlação e níveis de risco.
3. Painel web (linha do tempo, filtros).
4. Novas fontes: honeypot defensivo e scanner de segredos.
5. IA que explica (e só sobe o risco), relatórios em PDF e alertas.

## Como funciona (etapa 1)

```
NetSentinel ─┐
Anzol ───────┼─ POST /eventos (X-API-Key) ─> API FastAPI ─> PostgreSQL
(futuras) ───┘                              GET /eventos (filtros)
```

O formato do evento está em [docs/evento.md](docs/evento.md).

## Rodar com Docker

```bash
cp .env.example .env      # edite e preencha a chave e a senha
docker compose up --build
```

Documentação interativa: http://127.0.0.1:8000/docs

## Rodar sem Docker (SQLite local)

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows (Linux/macOS: source .venv/bin/activate)
pip install -r requirements-dev.txt
set ORBIT_CHAVE_API=minha-chave  # Windows (Linux/macOS: export ...)
uvicorn app.main:app --reload
```

## Exemplo de uso

```bash
curl -X POST http://127.0.0.1:8000/eventos \
  -H "X-API-Key: minha-chave" -H "Content-Type: application/json" \
  -d '{"origem":"anzol","tipo":"phishing_detectado","alvo":"maria@empresa.com.br",
       "nivel":"CRÍTICO","resumo":"E-mail com DMARC falhando."}'

curl -H "X-API-Key: minha-chave" "http://127.0.0.1:8000/eventos?nivel_minimo=ALTO"
```

## Testes

```bash
pytest
ruff check .
```

## Decisões de segurança

- **Falha fechada:** sem `ORBIT_CHAVE_API` configurada, a API recusa tudo (503).
- Chave comparada em tempo constante; segredos só em variáveis de ambiente.
- Entrada validada: campos extras recusados, tamanhos limitados, datas com fuso.
- No Docker, o banco não é exposto à rede e a API escuta só em `127.0.0.1`.
- O contêiner roda sem privilégios de root.

## Limites conhecidos (etapa 1)

- Uma única chave de API para todas as fontes (sem usuários nem papéis).
- Tabelas criadas na subida; falta migração (Alembic) para evoluir o banco.
- Sem limite de requisições por fonte (rate limit).
- Sem HTTPS: pensado para uso local ou atrás de um proxy.

## Licença

MIT
