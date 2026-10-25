"""Execução das migrações Alembic no startup (sem alembic.ini, compatível com build empacotado)."""
import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

BASELINE_REVISION = "0001_baseline"


def _migrations_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "backend" / "migrations"
    return Path(__file__).resolve().parents[2] / "migrations"


def make_config(connection) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_migrations_dir()))
    cfg.attributes["connection"] = connection
    return cfg


def _set_sqlite_foreign_keys(connection, enabled: bool) -> None:
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")
        connection.commit()  # encerra o autobegin do SQLAlchemy (o PRAGMA em si fica fora de transação)


def run_migrations(engine: Engine) -> None:
    """Cria o schema em bancos novos, adota bancos legados (criados via create_all) e aplica pendências.

    As FKs do SQLite ficam desligadas durante as migrações: o modo batch recria tabelas
    (DROP + RENAME) e, com elas ligadas, o DROP apagaria em cascata as linhas dependentes.
    """
    with engine.connect() as connection:
        _set_sqlite_foreign_keys(connection, False)  # PRAGMA não tem efeito dentro de transação
        try:
            with connection.begin():
                cfg = make_config(connection)
                tables = set(inspect(connection).get_table_names())
                if "books" in tables and "alembic_version" not in tables:
                    logger.info("Banco legado detectado: marcando baseline %s", BASELINE_REVISION)
                    command.stamp(cfg, BASELINE_REVISION)
                command.upgrade(cfg, "head")
        finally:
            _set_sqlite_foreign_keys(connection, True)  # a conexão volta para o pool
