import os
import sys
import tempfile
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

# Qt em modo offscreen (CI / ambientes sem tela)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# QSettings dos testes vão para uma pasta temporária, nunca para a configuração real do usuário
_SETTINGS_DIR = tempfile.mkdtemp(prefix="bookroom-test-settings-")
for _fmt in (QSettings.NativeFormat, QSettings.IniFormat):
    QSettings.setPath(_fmt, QSettings.UserScope, _SETTINGS_DIR)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def _no_real_backend(monkeypatch, tmp_path):
    """O singleton `api_client` nunca fala com um backend de verdade (o app pode estar aberto em :8010).

    Chamadas não simuladas falham na hora, como com a API offline; o cache de capas vai para uma pasta
    temporária. Testes que precisam da API usam a fixture `backend`.
    """
    import requests
    from frontend_desktop.api_client.client import api_client

    def offline(*_args, **_kwargs):
        raise requests.ConnectionError("rede desligada nos testes")
    monkeypatch.setattr(api_client._session, "request", offline)
    monkeypatch.setattr(api_client._session, "get", offline)
    monkeypatch.setattr(api_client, "cover_cache_dir", tmp_path / "cover-cache")


@pytest.fixture(autouse=True)
def _dispose_widgets(qapp):
    """Fecha e apaga (pelo Qt) as janelas de cada teste antes do próximo.

    Sem isso o coletor de lixo do Python destrói widgets em ciclo num momento qualquer (até no meio de
    outra chamada), o que derruba o processo com segfault.
    """
    yield
    import gc
    from PySide6.QtCore import QCoreApplication, QEvent
    from frontend_desktop.cover_loader import cover_loader
    cover_loader.wait_for_done(5000)  # capas pedidas no teste terminam antes de o backend/os widgets sumirem
    qapp.processEvents()
    cover_loader.invalidate()
    for widget in QApplication.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    qapp.processEvents()
    gc.collect()


@pytest.fixture(autouse=True)
def _clean_preferences():
    from frontend_desktop import preferences
    preferences.settings().clear()
    yield
    preferences.settings().clear()


def _sync_run_async(owner, func, on_success, on_error=None, *args, **kwargs):
    """Versão síncrona de workers.run_async (resultado entregue na hora, na mesma thread)."""
    try:
        result = func(*args, **kwargs)
    except Exception as exc:  # como o ApiWorker: o erro vira mensagem
        if on_error:
            on_error(str(exc))
        return None
    on_success(result)
    return None


ASYNC_MODULES = (
    "frontend_desktop.views.main_window",
    "frontend_desktop.views.components.next_queue_view",
    "frontend_desktop.views.components.yearbook_view",
    "frontend_desktop.views.components.management_view",
    "frontend_desktop.views.components.category_detail_view",
    "frontend_desktop.views.components.settings_view",
    "frontend_desktop.views.dialogs.book_dialog",
    "frontend_desktop.views.dialogs.book_dialog_cover",
    "frontend_desktop.views.dialogs.lookup_dialog",
)


@pytest.fixture
def sync_async(monkeypatch):
    import importlib
    for name in ASYNC_MODULES:
        monkeypatch.setattr(importlib.import_module(name), "run_async", _sync_run_async)


class _Adapter:
    """Faz o requests.Session do ApiClient falar com o TestClient do FastAPI (sem rede)."""

    def __init__(self, http, base):
        self.http, self.base = http, base

    def request(self, method, url, timeout=None, **kwargs):
        return self.http.request(method, url.replace(self.base, ""), **kwargs)

    def get(self, url, timeout=None, stream=False, **kwargs):
        return self.http.get(url.replace(self.base, ""), **kwargs)


@pytest.fixture
def backend(monkeypatch, tmp_path):
    """Backend real (banco em memória) atrás do `api_client`; devolve o TestClient para montar dados."""
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from backend.app.core.config import settings
    from backend.app.core.database import Base, get_db
    from backend.app.main import app
    from frontend_desktop.api_client.client import api_client

    monkeypatch.setattr(settings, "COVERS_DIR", tmp_path / "covers")
    settings.COVERS_DIR.mkdir()
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    app.dependency_overrides[get_db] = lambda: session
    http = TestClient(app)
    adapter = _Adapter(http, api_client.server_url)
    monkeypatch.setattr(api_client._session, "request", adapter.request)
    monkeypatch.setattr(api_client._session, "get", adapter.get)

    # As capas são lidas nas threads do QThreadPool: o TestClient (anyio) chamado de uma thread criada
    # pelo Qt derruba o processo de vez em quando, então elas vêm direto da pasta do backend
    def cover_path(filename):
        source = settings.COVERS_DIR / os.path.basename(filename or "")
        return str(source) if filename and source.is_file() else None
    monkeypatch.setattr(api_client, "get_cover_path", cover_path)
    try:
        yield http
    finally:
        from frontend_desktop.cover_loader import cover_loader
        cover_loader.wait_for_done(5000)  # threads de capa ainda podem estar usando o TestClient
        app.dependency_overrides.pop(get_db, None)
        session.close()
        engine.dispose()


@pytest.fixture
def add_book(backend):
    def create(**fields):
        res = backend.post("/api/v1/books/", json={"title": "Livro", **fields})
        assert res.status_code == 201, res.text
        return res.json()
    return create
