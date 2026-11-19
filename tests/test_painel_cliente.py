"""Cliente do painel contra uma API simulada (httpx.MockTransport, sem rede)."""

import httpx
import pytest

from painel.cliente import URL_PADRAO, ClienteOrbit, ErroDaApi, url_da_api

CHAVE = "chave-super-secreta-123"


def cliente_com(responder, chave=CHAVE):
    return ClienteOrbit("http://api.teste", chave, transport=httpx.MockTransport(responder))


def test_envia_chave_no_cabecalho_e_parametros():
    vistos = {}

    def responder(req):
        vistos["chave"] = req.headers.get("X-API-Key")
        vistos["params"] = dict(req.url.params)
        vistos["caminho"] = req.url.path
        return httpx.Response(200, json=[{"id": 1}])

    assert cliente_com(responder).listar_alertas({"limite": 10}) == [{"id": 1}]
    assert vistos == {"chave": CHAVE, "params": {"limite": "10"}, "caminho": "/alertas"}


def test_obter_alerta_usa_o_id():
    def responder(req):
        assert req.url.path == "/alertas/7"
        return httpx.Response(200, json={"id": 7, "eventos": []})

    assert cliente_com(responder).obter_alerta(7)["id"] == 7


@pytest.mark.parametrize(
    ("status", "trecho"),
    [(401, "recusou a chave"), (503, "sem chave configurada"), (404, "não encontrado"),
     (422, "filtros"), (500, "erro 500")],
)
def test_erros_http_viram_mensagem_em_portugues(status, trecho):
    with pytest.raises(ErroDaApi, match=trecho) as erro:
        cliente_com(lambda req: httpx.Response(status)).listar_eventos()
    assert CHAVE not in str(erro.value)


def test_api_fora_do_ar():
    def responder(req):
        raise httpx.ConnectError("conexão recusada")

    with pytest.raises(ErroDaApi, match="Não foi possível conectar") as erro:
        cliente_com(responder).listar_eventos()
    assert CHAVE not in str(erro.value)


def test_api_lenta():
    def responder(req):
        raise httpx.ReadTimeout("demorou")

    with pytest.raises(ErroDaApi, match="demorou demais"):
        cliente_com(responder).listar_eventos()


def test_sem_chave_nem_chama_a_api():
    def responder(req):
        raise AssertionError("não deveria chamar a API sem chave")

    with pytest.raises(ErroDaApi, match="ORBIT_CHAVE_API"):
        cliente_com(responder, chave="").listar_eventos()


def test_resposta_que_nao_e_json_ou_lista():
    with pytest.raises(ErroDaApi, match="não é JSON"):
        cliente_com(lambda req: httpx.Response(200, text="<html>")).listar_eventos()
    with pytest.raises(ErroDaApi, match="esperava uma lista"):
        cliente_com(lambda req: httpx.Response(200, json={"x": 1})).listar_eventos()


def test_repr_nao_mostra_a_chave():
    assert CHAVE not in repr(ClienteOrbit("http://api.teste", CHAVE))


def test_configuracao_vem_do_ambiente(monkeypatch):
    monkeypatch.delenv("ORBIT_API_URL", raising=False)
    assert url_da_api() == URL_PADRAO
    monkeypatch.setenv("ORBIT_API_URL", "http://api:8000/")
    assert url_da_api() == "http://api:8000"
