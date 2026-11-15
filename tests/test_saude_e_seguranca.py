def test_saude_e_publica(cliente):
    resposta = cliente.get("/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok"}


def test_eventos_sem_chave_da_401(cliente, evento_valido):
    assert cliente.post("/eventos", json=evento_valido).status_code == 401
    assert cliente.get("/eventos").status_code == 401


def test_chave_errada_da_401(cliente, evento_valido):
    resposta = cliente.post("/eventos", json=evento_valido, headers={"X-API-Key": "errada"})
    assert resposta.status_code == 401


def test_sem_chave_configurada_no_servidor_falha_fechada(cliente, cabecalho, monkeypatch):
    monkeypatch.delenv("ORBIT_CHAVE_API", raising=False)
    # Mesmo mandando um cabeçalho, nada é aceito: servidor sem chave = 503.
    assert cliente.get("/eventos", headers=cabecalho).status_code == 503
