import sqlalchemy as sa
from sqlalchemy import inspect

from backend.app.core.database import Base
from backend.app.core.migrations import run_migrations
import backend.app.models  # noqa: F401

HEAD_REVISION = "0001_baseline"


def _engine(tmp_path):
    return sa.create_engine(f"sqlite:///{tmp_path / 'test.db'}")


def test_new_database_gets_full_schema_and_version(tmp_path):
    engine = _engine(tmp_path)
    run_migrations(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"books", "authors", "genres", "publishers", "series", "book_authors", "book_genres",
            "yearbook_picks", "alembic_version"} <= tables
    with engine.connect() as c:
        assert c.execute(sa.text("select version_num from alembic_version")).scalar() == HEAD_REVISION


def test_migrations_are_idempotent(tmp_path):
    engine = _engine(tmp_path)
    run_migrations(engine)
    run_migrations(engine)


def test_database_created_without_alembic_is_adopted(tmp_path):
    engine = _engine(tmp_path)
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        c.execute(sa.text("insert into genres (name, color) values ('Fantasia', '#fff')"))
    run_migrations(engine)
    with engine.connect() as c:
        assert c.execute(sa.text("select name from genres")).scalar() == "Fantasia"
        assert c.execute(sa.text("select version_num from alembic_version")).scalar() == HEAD_REVISION


def test_models_and_migrations_have_no_drift(tmp_path):
    """Falha se um model mudar sem a migração correspondente."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    engine = _engine(tmp_path)
    run_migrations(engine)
    with engine.connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == []


def test_app_lifespan_runs_migrations(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import main
    engine = _engine(tmp_path)
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        assert client.get("/").status_code == 200
    assert "books" in inspect(engine).get_table_names()


def test_migrations_keep_foreign_keys_on(tmp_path):
    from backend.app.core import database
    engine = _engine(tmp_path)
    sa.event.listen(engine, "connect", database._enable_sqlite_foreign_keys)  # como no app
    run_migrations(engine)
    with engine.connect() as c:
        assert c.exec_driver_sql("pragma foreign_keys").scalar() == 1
