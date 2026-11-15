import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.banco import Base, criar_motor, obter_sessao
from app.main import app

CHAVE = "chave-de-teste"


@pytest.fixture
def cliente(monkeypatch):
    """Cliente de teste com banco em memória novo a cada teste e chave configurada."""
    monkeypatch.setenv("ORBIT_CHAVE_API", CHAVE)
    motor = criar_motor("sqlite:///:memory:")
    Base.metadata.create_all(motor)
    fabrica = sessionmaker(bind=motor, expire_on_commit=False)

    def sessao_de_teste():
        with fabrica() as sessao:
            yield sessao

    app.dependency_overrides[obter_sessao] = sessao_de_teste
    # Sem "with": não dispara o lifespan, então não toca no banco de verdade.
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def cabecalho():
    return {"X-API-Key": CHAVE}


@pytest.fixture
def evento_valido():
    return {
        "origem": "anzol",
        "tipo": "phishing_detectado",
        "alvo": "maria@empresa.com.br",
        "nivel": "CRÍTICO",
        "resumo": "E-mail com DMARC falhando e domínio parecido com marca.",
        "ocorrido_em": "2026-11-14T10:00:00Z",
        "detalhes": {"sinais": ["dmarc_falhou", "dominio_parecido_com_marca"]},
    }
