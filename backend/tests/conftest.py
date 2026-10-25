import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.core.config import settings
from backend.app.core.database import Base, get_db
from backend.app.main import app


@pytest.fixture(autouse=True)
def _isolated_covers_dir(tmp_path_factory, monkeypatch):
    """Nenhum teste lê ou apaga capas da pasta real (excluir/trocar capa remove o arquivo sem uso)."""
    monkeypatch.setattr(settings, "COVERS_DIR", tmp_path_factory.mktemp("covers"))


@pytest.fixture
def db_session():
    """Banco em memória novo para cada teste."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    """TestClient sem o lifespan (backup e migrações do banco real não rodam nos testes de API)."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def make_book(client):
    def create(**fields):
        payload = {"title": "Livro", **fields}
        res = client.post("/api/v1/books/", json=payload)
        assert res.status_code == 201, res.text
        return res.json()
    return create
