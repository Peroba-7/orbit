"""Cliente HTTP do painel: só leitura (GET /eventos, GET /alertas, GET /alertas/{id}).

A URL vem de ORBIT_API_URL e a chave de ORBIT_CHAVE_API. A chave nunca
aparece em mensagens, logs ou na tela. Qualquer falha vira `ErroDaApi` com
uma mensagem curta em português, sem stack trace.
"""

import os
from typing import Any

import httpx

URL_PADRAO = "http://127.0.0.1:8000"
TEMPO_LIMITE = 5.0  # segundos


class ErroDaApi(Exception):
    """Falha ao falar com a API, com mensagem pronta para mostrar ao usuário."""


def url_da_api() -> str:
    return (os.getenv("ORBIT_API_URL", "").strip() or URL_PADRAO).rstrip("/")


def chave_da_api() -> str | None:
    return os.getenv("ORBIT_CHAVE_API", "").strip() or None


class ClienteOrbit:
    def __init__(
        self,
        url: str | None = None,
        chave: str | None = None,
        transport: httpx.BaseTransport | None = None,  # usado nos testes
    ) -> None:
        self.url = (url or url_da_api()).rstrip("/")
        self._chave = chave if chave is not None else chave_da_api()
        self._transport = transport

    def __repr__(self) -> str:  # nunca expõe a chave
        return f"ClienteOrbit(url={self.url!r})"

    def _get(self, caminho: str, params: dict[str, Any] | None = None) -> Any:
        if not self._chave:
            raise ErroDaApi(
                "Chave de API não configurada. Defina ORBIT_CHAVE_API no ambiente do painel."
            )
        try:
            with httpx.Client(
                base_url=self.url, timeout=TEMPO_LIMITE, transport=self._transport
            ) as http:
                resposta = http.get(caminho, params=params, headers={"X-API-Key": self._chave})
        except httpx.TimeoutException:
            raise ErroDaApi(f"A API em {self.url} demorou demais para responder.") from None
        except (httpx.HTTPError, httpx.InvalidURL):
            raise ErroDaApi(
                f"Não foi possível conectar à API em {self.url}. Ela está no ar? "
                "Confira ORBIT_API_URL."
            ) from None

        if resposta.status_code == 401:
            raise ErroDaApi("A API recusou a chave (401). Confira ORBIT_CHAVE_API.")
        if resposta.status_code == 503:
            raise ErroDaApi(
                "A API está sem chave configurada (503) e recusa tudo. "
                "Defina ORBIT_CHAVE_API no servidor da API."
            )
        if resposta.status_code == 404:
            raise ErroDaApi("Registro não encontrado na API (404).")
        if resposta.status_code == 422:
            raise ErroDaApi("A API recusou os filtros informados (422).")
        if resposta.status_code >= 400:
            raise ErroDaApi(f"A API respondeu com erro {resposta.status_code}.")
        try:
            return resposta.json()
        except ValueError:
            raise ErroDaApi("A API devolveu uma resposta que não é JSON.") from None

    def listar_eventos(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._lista(self._get("/eventos", params))

    def listar_alertas(self, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return self._lista(self._get("/alertas", params))

    def obter_alerta(self, alerta_id: int) -> dict[str, Any]:
        corpo = self._get(f"/alertas/{int(alerta_id)}")
        if not isinstance(corpo, dict):
            raise ErroDaApi("Resposta inesperada da API para o alerta.")
        return corpo

    @staticmethod
    def _lista(corpo: Any) -> list[dict[str, Any]]:
        if not isinstance(corpo, list) or not all(isinstance(r, dict) for r in corpo):
            raise ErroDaApi("Resposta inesperada da API (esperava uma lista).")
        return corpo
