"""Popula o ORBIT com ~35 eventos FICTÍCIOS para demonstrar o painel.

    python scripts/popular_demo.py          # pede confirmação
    python scripts/popular_demo.py --sim    # sem perguntar (ex.: automação)

Usa ORBIT_API_URL (padrão http://127.0.0.1:8000) e ORBIT_CHAVE_API do ambiente.
Os dados são inventados: e-mails em exemplo.com.br e IPs só das faixas
reservadas para documentação (RFC 5737): 192.0.2.x, 198.51.100.x, 203.0.113.x.
As datas são relativas a "agora", para caírem nas janelas de correlação.

Cenários incluídos:
- maria@exemplo.com.br: phishing (Anzol) e depois login falho / brute force
  (NetSentinel) -> dispara "phishing_mais_login_falho" e "multiplas_fontes";
- 203.0.113.45: 3 varreduras ALTO em 40 min -> dispara "rajada_de_alertas";
- heartbeats (sinais de vida) de três sensores fictícios, para a regra de
  saúde das fontes (app/saude_fontes.py, limites padrão de 3 h e 7 dias):
  sensor-sede está ok, sensor-filial está SILENCIOSO (último sinal há 8 h) e
  anzol-gateway está DESATUALIZADO (regras de 20 dias atrás). Heartbeats não
  entram na correlação: não geram alertas de ataque;
- o resto: eventos isolados de vários níveis, que não devem gerar alerta.

NÃO rode contra um ORBIT de produção: os eventos ficam gravados de verdade.
"""

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

URL_PADRAO = "http://127.0.0.1:8000"


def _ev(
    agora: datetime, horas_atras: float, origem: str, tipo: str, alvo: str, nivel: str,
    resumo: str, **detalhes: Any,
) -> dict[str, Any]:
    return {
        "origem": origem,
        "tipo": tipo,
        "alvo": alvo,
        "nivel": nivel,
        "resumo": resumo,
        "ocorrido_em": (agora - timedelta(hours=horas_atras)).isoformat(),
        "detalhes": {"demo": True, **detalhes},
    }


def _heartbeat(
    agora: datetime, horas_atras: float, origem: str, sensor: str, versao_dias_atras: int
) -> dict[str, Any]:
    versao = (agora - timedelta(days=versao_dias_atras)).date().isoformat()
    return _ev(agora, horas_atras, origem, "heartbeat", sensor, "BAIXO",
               "Sinal de vida do sensor.", versao_regras=versao)


def eventos_demo(agora: datetime | None = None) -> list[dict[str, Any]]:
    """Lista fixa de eventos fictícios, com datas relativas a `agora`."""
    a = (agora or datetime.now(UTC)).replace(microsecond=0)
    return [
        # Cenário 1: phishing + login falho para a Maria (dispara alerta CRÍTICO).
        _ev(a, 6, "anzol", "phishing_detectado", "maria@exemplo.com.br", "ALTO",
            "E-mail com DMARC falhando e link para domínio parecido com o do banco.",
            sinais=["dmarc_falhou", "dominio_parecido_com_marca"]),
        _ev(a, 4, "netsentinel", "login_falho", "maria@exemplo.com.br", "MÉDIO",
            "Login falho na VPN a partir de 198.51.100.23.", ip="198.51.100.23"),
        _ev(a, 3.8, "netsentinel", "brute_force", "maria@exemplo.com.br", "ALTO",
            "12 tentativas de senha em 2 minutos a partir de 198.51.100.23.",
            ip="198.51.100.23", tentativas=12),
        # Cenário 2: rajada de eventos graves no mesmo IP (3 em 40 min).
        _ev(a, 2.0, "netsentinel", "varredura_de_portas", "203.0.113.45", "ALTO",
            "Varredura em 1.024 portas TCP.", portas=1024),
        _ev(a, 1.8, "netsentinel", "varredura_de_portas", "203.0.113.45", "ALTO",
            "Nova varredura, agora em portas UDP.", portas=200),
        _ev(a, 1.35, "netsentinel", "exploracao_tentada", "203.0.113.45", "CRÍTICO",
            "Tentativa de exploração em serviço SSH exposto."),
        # Eventos isolados (não devem gerar alerta).
        _ev(a, 30, "anzol", "phishing_detectado", "joao@exemplo.com.br", "MÉDIO",
            "Anexo .html suspeito em e-mail de remetente desconhecido."),
        _ev(a, 28, "anzol", "spam", "ana@exemplo.com.br", "BAIXO",
            "Propaganda em massa, sem link perigoso."),
        _ev(a, 26, "netsentinel", "conexao_bloqueada", "192.0.2.10", "BAIXO",
            "Conexão de saída bloqueada para porta incomum."),
        _ev(a, 25, "anzol", "remetente_falsificado", "financeiro@exemplo.com.br", "ALTO",
            "Remetente se passando pela diretoria pedindo transferência."),
        _ev(a, 23, "netsentinel", "dns_suspeito", "192.0.2.15", "MÉDIO",
            "Consulta DNS a domínio recém-registrado."),
        _ev(a, 22, "anzol", "spam", "carlos@exemplo.com.br", "BAIXO",
            "Boletim não solicitado."),
        _ev(a, 20, "netsentinel", "conexao_bloqueada", "192.0.2.22", "BAIXO",
            "Tentativa de acesso a porta 23 (telnet) bloqueada."),
        _ev(a, 19, "anzol", "phishing_detectado", "bianca@exemplo.com.br", "ALTO",
            "Página falsa de login do e-mail corporativo.", sinais=["pagina_clonada"]),
        _ev(a, 17, "netsentinel", "trafego_incomum", "198.51.100.77", "MÉDIO",
            "Volume de upload 5x acima do normal para o horário."),
        _ev(a, 16, "anzol", "anexo_malicioso", "rh@exemplo.com.br", "ALTO",
            "Planilha com macro que baixa executável."),
        _ev(a, 14, "netsentinel", "conexao_bloqueada", "192.0.2.31", "BAIXO",
            "Conexão bloqueada pela política padrão."),
        _ev(a, 12, "anzol", "spam", "pedro@exemplo.com.br", "BAIXO",
            "Oferta de produto genérica."),
        _ev(a, 11, "netsentinel", "dns_suspeito", "198.51.100.90", "MÉDIO",
            "Muitas consultas DNS para subdomínios aleatórios."),
        _ev(a, 10, "anzol", "dominio_parecido", "compras@exemplo.com.br", "MÉDIO",
            "Domínio do remetente difere do oficial por uma letra."),
        _ev(a, 9, "netsentinel", "certificado_invalido", "192.0.2.40", "BAIXO",
            "Servidor interno com certificado expirado."),
        _ev(a, 8, "anzol", "spam", "lucas@exemplo.com.br", "BAIXO",
            "Lista de e-mails comprada."),
        _ev(a, 7, "netsentinel", "trafego_incomum", "203.0.113.80", "MÉDIO",
            "Conexões repetidas em horário fora do expediente."),
        _ev(a, 5, "anzol", "phishing_detectado", "julia@exemplo.com.br", "MÉDIO",
            "Link encurtado levando a formulário externo."),
        _ev(a, 4.5, "netsentinel", "conexao_bloqueada", "192.0.2.55", "BAIXO",
            "Conexão bloqueada para país fora da lista permitida."),
        _ev(a, 3, "anzol", "spam", "marcos@exemplo.com.br", "BAIXO",
            "Newsletter sem descadastro."),
        _ev(a, 2.5, "netsentinel", "dns_suspeito", "198.51.100.120", "MÉDIO",
            "Consulta a domínio de lista de bloqueio."),
        _ev(a, 1, "anzol", "remetente_falsificado", "diretoria@exemplo.com.br", "ALTO",
            "E-mail imitando fornecedor com troca de dados bancários."),
        _ev(a, 0.5, "netsentinel", "certificado_invalido", "192.0.2.60", "BAIXO",
            "Certificado autoassinado em impressora de rede."),
        _ev(a, 0.2, "anzol", "spam", "paula@exemplo.com.br", "BAIXO",
            "Promoção genérica."),
        # Saúde das fontes: heartbeats (sinal de vida + versão das regras).
        _heartbeat(a, 1.25, "netsentinel", "sensor-sede", versao_dias_atras=1),
        _heartbeat(a, 0.25, "netsentinel", "sensor-sede", versao_dias_atras=1),  # ok
        _heartbeat(a, 8, "netsentinel", "sensor-filial", versao_dias_atras=2),  # silencioso
        _heartbeat(a, 0.1, "anzol", "anzol-gateway", versao_dias_atras=20),  # desatualizado
    ]


def confirmar(url: str, quantidade: int) -> bool:
    print(f"Vou enviar {quantidade} eventos FICTÍCIOS para {url}.")
    print("Eles ficam gravados de verdade e podem gerar alertas. Não use em produção.")
    if not sys.stdin.isatty():
        print("Entrada não interativa: use --sim para confirmar.")
        return False
    try:
        resposta = input("Continuar? [s/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return resposta.strip().lower() in ("s", "sim")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Popula o ORBIT com eventos fictícios.")
    parser.add_argument("--sim", action="store_true", help="não pede confirmação")
    args = parser.parse_args(argv)

    url = (os.getenv("ORBIT_API_URL", "").strip() or URL_PADRAO).rstrip("/")
    chave = os.getenv("ORBIT_CHAVE_API", "").strip()
    if not chave:
        print("Defina ORBIT_CHAVE_API no ambiente antes de rodar.", file=sys.stderr)
        return 2

    eventos = eventos_demo()
    if not args.sim and not confirmar(url, len(eventos)):
        print("Nada foi enviado.")
        return 1

    enviados = 0
    try:
        with httpx.Client(base_url=url, timeout=10, headers={"X-API-Key": chave}) as http:
            for evento in eventos:
                resposta = http.post("/eventos", json=evento)
                if resposta.status_code != 201:
                    print(f"Falhou ({resposta.status_code}) no evento {evento['tipo']} "
                          f"para {evento['alvo']}. Parando.", file=sys.stderr)
                    return 1
                enviados += 1
            alertas = http.get("/alertas", params={"limite": 200})
    except httpx.HTTPError:
        print(f"Não foi possível falar com a API em {url}. Ela está no ar?", file=sys.stderr)
        return 1

    print(f"{enviados} eventos enviados.")
    if alertas.status_code == 200:
        print(f"A API tem agora {len(alertas.json())} alerta(s). Veja no painel.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
