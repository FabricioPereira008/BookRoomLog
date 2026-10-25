from alembic import context

from backend.app.core.database import Base
import backend.app.models  # noqa: F401  (registra todos os models no metadata)

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    # A engine/conexão é injetada por backend.app.core.migrations.run_migrations
    connection = config.attributes["connection"]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,  # SQLite: ALTER TABLE via recriação de tabela
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
