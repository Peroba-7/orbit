"""Conexão com o banco e as tabelas de eventos e alertas (SQLAlchemy 2.0).

Esquemas (esquemas.py) descrevem o que trafega pela API; os modelos daqui
descrevem como o dado fica guardado no banco. São coisas diferentes.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Index,
    String,
    TypeDecorator,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import url_do_banco


class Base(DeclarativeBase):
    pass


class DataUTC(TypeDecorator):
    """Data/hora sempre em UTC, com fuso, não importa o banco.

    O PostgreSQL guarda o fuso, mas o SQLite não: ele devolveria datas "ingênuas".
    Este tipo converte para UTC ao gravar e devolve com fuso UTC ao ler.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, valor: datetime | None, dialect) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            raise ValueError("data sem fuso horário")
        return valor.astimezone(UTC)

    def process_result_value(self, valor: datetime | None, dialect) -> datetime | None:
        if valor is None:
            return None
        if valor.tzinfo is None:
            return valor.replace(tzinfo=UTC)
        return valor.astimezone(UTC)


class Evento(Base):
    __tablename__ = "eventos"
    __table_args__ = (
        Index("ix_eventos_ocorrido_em", "ocorrido_em"),
        Index("ix_eventos_alvo", "alvo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    origem: Mapped[str] = mapped_column(String(40))
    tipo: Mapped[str] = mapped_column(String(80))
    alvo: Mapped[str] = mapped_column(String(255))
    nivel: Mapped[str] = mapped_column(String(10))
    resumo: Mapped[str] = mapped_column(String(500))
    detalhes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    ocorrido_em: Mapped[datetime] = mapped_column(DataUTC())
    recebido_em: Mapped[datetime] = mapped_column(DataUTC(), default=lambda: datetime.now(UTC))


class Alerta(Base):
    """Alerta criado pelo motor de correlação (app/correlacao.py).

    `assinatura` é um hash dos ids dos eventos. Junto com regra e alvo, forma
    uma chave única: o mesmo alerta (mesma regra, alvo e conjunto de eventos)
    nunca é gravado duas vezes, nem com duas requisições ao mesmo tempo.
    """

    __tablename__ = "alertas"
    __table_args__ = (
        UniqueConstraint("regra", "alvo", "assinatura", name="uq_alertas_regra_alvo_eventos"),
        Index("ix_alertas_alvo", "alvo"),
        Index("ix_alertas_criado_em", "criado_em"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    regra: Mapped[str] = mapped_column(String(60))
    nivel: Mapped[str] = mapped_column(String(10))
    alvo: Mapped[str] = mapped_column(String(255))
    resumo: Mapped[str] = mapped_column(String(500))
    eventos_ids: Mapped[list[int]] = mapped_column(JSON)
    assinatura: Mapped[str] = mapped_column(String(64))
    criado_em: Mapped[datetime] = mapped_column(DataUTC(), default=lambda: datetime.now(UTC))


def criar_motor(url: str | None = None) -> Engine:
    url = url or url_do_banco()
    if url.startswith("sqlite") and ":memory:" in url:
        # Banco em memória (testes): uma única conexão compartilhada.
        return create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


motor = criar_motor()
FabricaDeSessao = sessionmaker(bind=motor, expire_on_commit=False)


def criar_tabelas(engine: Engine | None = None) -> None:
    Base.metadata.create_all(engine or motor)


def obter_sessao() -> Iterator[Session]:
    """Dependência do FastAPI: abre uma sessão por requisição e fecha no fim."""
    with FabricaDeSessao() as sessao:
        yield sessao
