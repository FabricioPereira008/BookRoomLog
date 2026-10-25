"""Capas sem uso: apagadas ao excluir/trocar a capa de um livro e na limpeza manual."""
import os
import time

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.book import Book
from backend.app.services import cover_service

@pytest.fixture
def db(db_session):
    app.dependency_overrides[get_db] = lambda: db_session
    yield db_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def covers(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "COVERS_DIR", tmp_path)
    return tmp_path


def _file(folder, name, age_seconds=7200, size=10):
    path = folder / name
    path.write_bytes(b"x" * size)
    old = time.time() - age_seconds
    os.utime(path, (old, old))
    return name


def _book(client, title, cover=None):
    return client.post("/api/v1/books/", json={"title": title, "cover_image": cover}).json()


def test_delete_book_removes_its_cover_but_keeps_shared_ones(db, covers):
    client = TestClient(app)
    own = _file(covers, "own.jpg")
    shared = _file(covers, "shared.jpg")
    a, b, c = _book(client, "A", own), _book(client, "B", shared), _book(client, "C", shared)
    assert client.delete(f"/api/v1/books/{a['id']}").status_code == 204
    assert not (covers / own).exists()
    client.delete(f"/api/v1/books/{b['id']}")
    assert (covers / shared).exists()                       # C ainda usa
    client.delete(f"/api/v1/books/{c['id']}")
    assert not (covers / shared).exists()


def test_changing_cover_removes_the_old_file(db, covers):
    client = TestClient(app)
    old, new = _file(covers, "old.jpg"), _file(covers, "new.jpg")
    book = _book(client, "A", old)
    client.put(f"/api/v1/books/{book['id']}", json={"title": "A renomeado"})
    assert (covers / old).exists()                          # capa não mudou
    client.put(f"/api/v1/books/{book['id']}", json={"cover_image": new})
    assert not (covers / old).exists() and (covers / new).exists()
    client.put(f"/api/v1/books/{book['id']}", json={"cover_image": None})
    assert not (covers / new).exists()


def test_auto_cover_replaces_and_discards_old(db, covers, monkeypatch):
    from backend.app.api.v1.endpoints import uploads
    client = TestClient(app)
    old, new = _file(covers, "old.jpg"), _file(covers, "new.jpg")
    book = _book(client, "Duna", old)

    async def fake_find(title, author=None, isbn=None, api_key=None):
        return new, "teste"
    monkeypatch.setattr(uploads, "find_cover", fake_find)
    r = client.post(f"/api/v1/uploads/auto-cover-book/{book['id']}", json={})
    assert r.json()["success"] and not (covers / old).exists()


def test_discard_ignores_missing_or_unlinkable_files(db, covers, monkeypatch):
    assert cover_service.discard_cover_if_unused(db, None) is False
    assert cover_service.discard_cover_if_unused(db, "nao-existe.jpg") is False
    name = _file(covers, "x.jpg")
    monkeypatch.setattr(type(covers / name), "unlink", lambda self, *a, **k: (_ for _ in ()).throw(OSError("ocupado")))
    assert cover_service.discard_cover_if_unused(db, name) is False


def test_orphans_skip_used_recent_and_non_images(db, covers):
    db.add(Book(title="A", cover_image=_file(covers, "used.jpg")))
    db.commit()
    _file(covers, "orphan.png", size=300)
    _file(covers, "recent.jpg", age_seconds=10)            # pode estar num diálogo ainda aberto
    _file(covers, "notes.txt")
    assert [p.name for p in cover_service.orphan_covers(db)] == ["orphan.png"]
    assert cover_service.orphan_covers_summary(db) == {"count": 1, "bytes": 300}


def test_orphan_endpoints(db, covers):
    client = TestClient(app)
    _book(client, "A", _file(covers, "used.jpg"))
    _file(covers, "o1.jpg", size=100)
    _file(covers, "o2.webp", size=50)
    assert client.get("/api/v1/uploads/covers/orphans").json() == {"count": 2, "bytes": 150}
    assert client.post("/api/v1/uploads/covers/cleanup").json() == {"removed": 2, "freed_bytes": 150}
    assert sorted(p.name for p in covers.iterdir()) == ["used.jpg"]
    assert client.post("/api/v1/uploads/covers/cleanup").json() == {"removed": 0, "freed_bytes": 0}


def test_orphans_without_covers_folder(db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "COVERS_DIR", tmp_path / "nao-existe")
    assert cover_service.orphan_covers(db) == []
