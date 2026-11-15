"""Autenticação por chave de API (cabeçalho X-API-Key).

Regras:
- sem chave configurada no servidor -> 503 (falha fechada, nada é aceito);
- chave ausente ou errada -> 401;
- comparação em tempo constante (hmac.compare_digest) para não vazar a chave
  por diferença de tempo de resposta.
"""

import hmac

from fastapi import Header, HTTPException, status

from app.config import chave_da_api


def exigir_chave(x_api_key: str | None = Header(default=None)) -> None:
    esperada = chave_da_api()
    if esperada is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Servidor sem chave de API configurada.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, esperada):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chave de API inválida.")
