def test_registrar_e_buscar_evento(cliente, cabecalho, evento_valido):
    criado = cliente.post("/eventos", json=evento_valido, headers=cabecalho)
    assert criado.status_code == 201
    corpo = criado.json()
    assert corpo["id"] >= 1
    assert corpo["origem"] == "anzol"
    assert corpo["nivel"] == "CRÍTICO"
    assert corpo["recebido_em"]

    buscado = cliente.get(f"/eventos/{corpo['id']}", headers=cabecalho)
    assert buscado.status_code == 200
    assert buscado.json()["alvo"] == "maria@empresa.com.br"


def test_evento_inexistente_da_404(cliente, cabecalho):
    assert cliente.get("/eventos/999", headers=cabecalho).status_code == 404


def test_origem_desconhecida_da_422(cliente, cabecalho, evento_valido):
    evento_valido["origem"] = "inventada"
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_nivel_desconhecido_da_422(cliente, cabecalho, evento_valido):
    evento_valido["nivel"] = "ENORME"
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_campo_extra_e_recusado(cliente, cabecalho, evento_valido):
    evento_valido["id"] = 1  # a fonte não escolhe o id
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_data_sem_fuso_e_recusada(cliente, cabecalho, evento_valido):
    evento_valido["ocorrido_em"] = "2026-11-14T10:00:00"
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_ocorrido_em_omitido_vale_agora(cliente, cabecalho, evento_valido):
    del evento_valido["ocorrido_em"]
    resposta = cliente.post("/eventos", json=evento_valido, headers=cabecalho)
    assert resposta.status_code == 201
    assert resposta.json()["ocorrido_em"]


def test_texto_vazio_ou_so_espacos_e_recusado(cliente, cabecalho, evento_valido):
    evento_valido["alvo"] = "   "
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_detalhes_muito_grandes_sao_recusados(cliente, cabecalho, evento_valido):
    evento_valido["detalhes"] = {"lixo": "x" * 9000}
    assert cliente.post("/eventos", json=evento_valido, headers=cabecalho).status_code == 422


def test_listagem_filtra_por_origem_alvo_e_nivel(cliente, cabecalho, evento_valido):
    def enviar(**mudancas):
        corpo = {**evento_valido, **mudancas}
        assert cliente.post("/eventos", json=corpo, headers=cabecalho).status_code == 201

    enviar(origem="anzol", nivel="BAIXO", alvo="a@x.com")
    enviar(origem="anzol", nivel="ALTO", alvo="b@x.com")
    enviar(origem="netsentinel", nivel="CRÍTICO", alvo="10.0.0.5")

    def listar(**params):
        resposta = cliente.get("/eventos", params=params, headers=cabecalho)
        assert resposta.status_code == 200
        return resposta.json()

    assert len(listar()) == 3
    assert len(listar(origem="anzol")) == 2
    assert len(listar(alvo="10.0.0.5")) == 1
    assert {e["nivel"] for e in listar(nivel_minimo="ALTO")} == {"ALTO", "CRÍTICO"}
    assert len(listar(limite=1)) == 1


def test_listagem_vem_do_mais_recente_para_o_mais_antigo(cliente, cabecalho, evento_valido):
    for hora in ("08", "12", "10"):
        corpo = {**evento_valido, "ocorrido_em": f"2026-11-14T{hora}:00:00Z"}
        cliente.post("/eventos", json=corpo, headers=cabecalho)
    horas = [e["ocorrido_em"][11:13] for e in cliente.get("/eventos", headers=cabecalho).json()]
    assert horas == ["12", "10", "08"]


def test_limite_acima_do_maximo_da_422(cliente, cabecalho):
    assert cliente.get("/eventos", params={"limite": 1000}, headers=cabecalho).status_code == 422
