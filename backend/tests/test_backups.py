import io
import json
import sqlite3
import zipfile

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from backend.app.core.migrations import run_migrations
from backend.app.main import app
from backend.app.api.v1.endpoints import backups as backups_endpoint
from backend.app.core.config import settings
from backend.app.services import backup_service as bs


@pytest.fixture(autouse=True)
def covers_dir(tmp_path, monkeypatch):
    """Pasta de capas "ao vivo" isolada por teste."""
    folder = tmp_path / "live-covers"
    folder.mkdir()
    monkeypatch.setattr(settings, "COVERS_DIR", folder)
    return folder


def _engine(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'bookroom.db'}")
    run_migrations(engine)
    return engine


def _add_book(engine, title, cover=None):
    with engine.begin() as c:
        c.execute(sa.text(
            "insert into books (title, status, format, read_number, is_favorite, created_at, updated_at, "
            "cover_image) values (:t, 'QUERO_LER', 'EBOOK', 1, 0, '2026-01-01', '2026-01-01', :c)"),
            {"t": title, "c": cover})


def _cover(folder, name, data=b"img"):
    (folder / name).write_bytes(data)
    return name


def _titles(engine):
    with engine.connect() as c:
        return sorted(r[0] for r in c.execute(sa.text("select title from books")))


def test_paths_and_memory_database(tmp_path):
    engine = _engine(tmp_path)
    assert bs.backup_dir(engine) == (tmp_path / "backups").resolve()
    memory = sa.create_engine("sqlite://")
    assert bs.backup_dir(memory) is None and bs.list_backups(memory) == []
    assert bs.auto_backup(memory) is None
    with pytest.raises(bs.InvalidBackupError):
        bs.create_backup(memory)


def test_auto_backup_once_a_day_and_skips_new_database(tmp_path):
    empty = sa.create_engine(f"sqlite:///{tmp_path / 'novo.db'}")
    assert bs.auto_backup(empty) is None  # banco novo, sem tabelas

    engine = _engine(tmp_path)
    _add_book(engine, "Duna")
    first = bs.auto_backup(engine)
    assert first["reason"] == "auto" and first["books_count"] == 1
    assert bs.auto_backup(engine) is None  # já tem backup hoje
    listed = bs.list_backups(engine)
    assert [b["name"] for b in listed] == [first["name"]] and listed[0]["reason_label"] == "Automático"


def test_rotation_keeps_the_newest(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    folder = bs.backup_dir(engine)
    folder.mkdir()
    for day in range(1, 13):
        (folder / f"bookroom-202601{day:02d}-120000.db").write_bytes(b"")
    (folder / "outro-arquivo.txt").write_text("não mexer")
    bs.create_backup(engine)
    names = sorted(p.name for p in folder.iterdir() if p.suffix == ".db")
    assert len(names) == bs.MAX_BACKUPS and "bookroom-20260101-120000.db" not in names
    assert (folder / "outro-arquivo.txt").exists()
    broken = [b for b in bs.list_backups(engine) if b["name"].startswith("bookroom-202601")]
    assert broken and broken[0]["books_count"] is None  # arquivo vazio: contagem desconhecida


def test_restore_replaces_data_saves_current_state_and_migrates(tmp_path):
    engine = _engine(tmp_path)
    _add_book(engine, "Antes")
    saved = bs.create_backup(engine)
    _add_book(engine, "Depois")
    migrated = []
    result = bs.restore_backup(engine, saved["name"], lambda e: migrated.append(e) or run_migrations(e))
    assert _titles(engine) == ["Antes"] and migrated == [engine]
    safety = next(b for b in bs.list_backups(engine) if b["name"] == result["safety_backup"])
    assert safety["reason"] == "antes-da-restauracao" and safety["books_count"] == 2

    with pytest.raises(bs.InvalidBackupError):
        bs.restore_backup(engine, "../bookroom.db", run_migrations)
    with pytest.raises(bs.BackupNotFoundError):
        bs.restore_backup(engine, "bookroom-20990101-000000.db", run_migrations)
    junk = bs.backup_dir(engine) / "bookroom-20200101-000000.db"
    junk.write_text("não é sqlite")
    with pytest.raises(bs.InvalidBackupError):
        bs.restore_backup(engine, junk.name, run_migrations)
    assert _titles(engine) == ["Antes"]


def test_restore_oldest_with_full_rotation_keeps_it_until_restored(tmp_path):
    engine = _engine(tmp_path)
    _add_book(engine, "Velho")
    oldest = bs.create_backup(engine)
    folder = bs.backup_dir(engine)
    for day in range(1, bs.MAX_BACKUPS):
        with sqlite3.connect(folder / f"bookroom-2099{day:04d}-000000.db") as c:
            c.execute("create table books (id integer)")
    _add_book(engine, "Novo")
    bs.restore_backup(engine, oldest["name"], run_migrations)
    assert _titles(engine) == ["Velho"]
    assert len([p for p in folder.iterdir() if bs.NAME_RE.match(p.name)]) == bs.MAX_BACKUPS


@pytest.fixture
def client(tmp_path):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna")
    app.dependency_overrides[backups_endpoint.get_engine] = lambda: engine
    yield TestClient(app), engine
    app.dependency_overrides.pop(backups_endpoint.get_engine, None)


def test_backup_endpoints(client):
    http, engine = client
    empty = http.get("/api/v1/backups/").json()
    assert empty["backups"] == [] and empty["max_backups"] == bs.MAX_BACKUPS and empty["folder"].endswith("backups")
    created = http.post("/api/v1/backups/")
    assert created.status_code == 201 and created.json()["reason"] == "manual"
    _add_book(engine, "Emma")
    restored = http.post(f"/api/v1/backups/{created.json()['name']}/restore")
    assert restored.status_code == 200 and _titles(engine) == ["Duna"]
    assert len(http.get("/api/v1/backups/").json()["backups"]) == 2
    assert http.post("/api/v1/backups/bookroom-20990101-000000.db/restore").status_code == 404
    assert http.post("/api/v1/backups/qualquer.db/restore").status_code == 400

    app.dependency_overrides[backups_endpoint.get_engine] = lambda: sa.create_engine("sqlite://")
    assert http.post("/api/v1/backups/").status_code == 400


def test_lifespan_backs_up_before_migrating(tmp_path, monkeypatch):
    from backend.app import main
    engine = _engine(tmp_path)
    _add_book(engine, "Duna")
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app):
        pass
    assert [b["reason"] for b in bs.list_backups(engine)] == ["auto"]


# --- capas no backup ---

def test_backup_mirrors_covers_and_restore_brings_them_back(tmp_path, covers_dir):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna", _cover(covers_dir, "a1.webp", b"capa-hades"))
    saved = bs.create_backup(engine)
    mirror = bs.backup_dir(engine) / bs.COVERS_SUBDIR
    assert (mirror / "a1.webp").read_bytes() == b"capa-hades"

    (covers_dir / "a1.webp").unlink()                       # capa perdida
    result = bs.restore_backup(engine, saved["name"], run_migrations)
    assert result["covers_restored"] == 1 and (covers_dir / "a1.webp").read_bytes() == b"capa-hades"
    again = bs.restore_backup(engine, saved["name"], run_migrations)
    assert again["covers_restored"] == 0                    # já estava lá: não sobrescreve


def test_mirror_drops_covers_no_backup_uses(tmp_path, covers_dir):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna", _cover(covers_dir, "usada.png"))
    _cover(covers_dir, "orfa.png")                          # nenhum livro usa
    _cover(covers_dir, "nao-e-capa.txt")
    bs.create_backup(engine)
    mirror = bs.backup_dir(engine) / bs.COVERS_SUBDIR
    assert sorted(p.name for p in mirror.iterdir()) == ["usada.png"]


def test_mirror_kept_when_a_backup_is_unreadable(tmp_path, covers_dir):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna", _cover(covers_dir, "usada.png"))
    folder = bs.backup_dir(engine)
    folder.mkdir()
    (folder / "bookroom-20200101-000000.db").write_text("lixo")
    mirror = folder / bs.COVERS_SUBDIR
    mirror.mkdir()
    (mirror / "antiga.png").write_bytes(b"x")
    bs.create_backup(engine)
    assert (mirror / "antiga.png").exists()                 # na dúvida, não apaga


def test_backup_survives_cover_copy_failure(tmp_path, covers_dir, monkeypatch):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna")
    monkeypatch.setattr(bs, "_mirror_covers", lambda folder: (_ for _ in ()).throw(OSError("disco cheio")))
    assert bs.create_backup(engine)["books_count"] == 1


def test_backup_without_covers_folder(tmp_path, covers_dir, monkeypatch):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna")
    monkeypatch.setattr(settings, "COVERS_DIR", tmp_path / "nao-existe")
    assert bs.create_backup(engine)["books_count"] == 1


# --- exportar / importar .zip ---

def _export(engine, name):
    buffer = io.BytesIO()
    count = bs.export_backup(engine, name, buffer)
    buffer.seek(0)
    return buffer, count


def _zip(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, data in entries.items():
            archive.writestr(path, data)
    buffer.seek(0)
    return buffer


def test_export_contains_database_covers_and_manifest(tmp_path, covers_dir):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna", _cover(covers_dir, "a1.webp"))
    _add_book(engine, "Emma", "sumiu.png")               # referenciada, mas o arquivo não existe
    saved = bs.create_backup(engine)
    buffer, count = _export(engine, saved["name"])
    with zipfile.ZipFile(buffer) as archive:
        names = set(archive.namelist())
        manifest = json.loads(archive.read(bs.ARCHIVE_MANIFEST))
    assert count == 1 and names == {"manifest.json", "bookroom.db", "covers/a1.webp"}
    assert manifest["format"] == bs.ARCHIVE_FORMAT and manifest["books_count"] == 2
    assert manifest["covers_count"] == 1 and manifest["covers_missing"] == 1


def test_import_round_trip_on_another_computer(tmp_path, covers_dir, monkeypatch):
    engine = _engine(tmp_path)
    _add_book(engine, "Duna", _cover(covers_dir, "a1.webp", b"capa"))
    buffer, _ = _export(engine, bs.create_backup(engine)["name"])

    other_dir = tmp_path / "outro-pc"
    other_dir.mkdir()
    other = _engine(other_dir)
    new_covers = other_dir / "covers"
    monkeypatch.setattr(settings, "COVERS_DIR", new_covers)
    imported = bs.import_backup(other, buffer)
    assert imported["reason"] == "importado" and imported["reason_label"] == "Importado"
    assert imported["books_count"] == 1
    bs.restore_backup(other, imported["name"], run_migrations)
    assert _titles(other) == ["Duna"] and (new_covers / "a1.webp").read_bytes() == b"capa"


@pytest.mark.parametrize("entries, message", [
    ({"qualquer.txt": "x"}, "não é um backup"),
    ({"manifest.json": json.dumps({"format": "outro"}), "bookroom.db": "x"}, "não é um backup"),
    ({"manifest.json": "{quebrado", "bookroom.db": "x"}, "não é um backup"),
    ({"manifest.json": json.dumps({"format": "bookroom-backup", "version": 99}), "bookroom.db": "x"}, "mais nova"),
    ({"manifest.json": json.dumps({"format": "bookroom-backup", "version": 1}), "bookroom.db": "x",
      "covers/../../fora.png": "x"}, "inesperado"),
    ({"manifest.json": json.dumps({"format": "bookroom-backup", "version": 1}), "bookroom.db": "x",
      "outra/pasta.png": "x"}, "inesperado"),
    ({"manifest.json": json.dumps({"format": "bookroom-backup", "version": 1}), "bookroom.db": "não é sqlite"},
     "banco do BookRoom"),
])
def test_import_rejects_bad_archives(tmp_path, entries, message):
    engine = _engine(tmp_path)
    with pytest.raises(bs.InvalidBackupError, match=message):
        bs.import_backup(engine, _zip(entries))
    assert bs.list_backups(engine) == []


def test_import_rejects_non_zip_huge_and_oversized_cover(tmp_path, monkeypatch):
    engine = _engine(tmp_path)
    with pytest.raises(bs.InvalidBackupError):
        bs.import_backup(engine, io.BytesIO(b"nao e zip"))
    good = {"manifest.json": json.dumps({"format": "bookroom-backup", "version": 1}), "bookroom.db": "x",
            "covers/a.png": "123456"}
    monkeypatch.setattr(settings, "MAX_COVER_BYTES", 3)
    with pytest.raises(bs.InvalidBackupError, match="inesperado"):
        bs.import_backup(engine, _zip(good))
    monkeypatch.setattr(settings, "MAX_COVER_BYTES", 100)
    monkeypatch.setattr(bs, "MAX_ARCHIVE_BYTES", 5)
    with pytest.raises(bs.InvalidBackupError, match="grande demais"):
        bs.import_backup(engine, _zip(good))
    with pytest.raises(bs.InvalidBackupError):
        bs.import_backup(sa.create_engine("sqlite://"), _zip(good))


def test_export_and_import_endpoints(client):
    http, engine = client
    name = http.post("/api/v1/backups/").json()["name"]
    response = http.get(f"/api/v1/backups/{name}/export")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert name.removesuffix(".db") + ".zip" in response.headers["content-disposition"]
    imported = http.post("/api/v1/backups/import", files={"file": ("b.zip", response.content, "application/zip")})
    assert imported.status_code == 201 and imported.json()["reason"] == "importado"
    assert http.get("/api/v1/backups/bookroom-20990101-000000.db/export").status_code == 404
    assert http.get("/api/v1/backups/qualquer.db/export").status_code == 400
    bad = http.post("/api/v1/backups/import", files={"file": ("b.zip", b"lixo", "application/zip")})
    assert bad.status_code == 400
