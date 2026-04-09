import asyncio
from logging.config import fileConfig

import alembic_postgresql_enum  # noqa: F401 — registers enum migration support
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from alembic.script import ScriptDirectory

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.config import settings  # noqa: E402
from app.models import User, Method, Book, BookChapter, Class, SubjectModel, Classroom  # noqa: F401, E402
from sqlmodel import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata

config.set_main_option("sqlalchemy.url", settings.database_url)
MAX_ALEMBIC_REVISION_LEN = 32


def validate_revision_id_lengths() -> None:
    script = ScriptDirectory.from_config(config)
    offenders: list[tuple[str, str]] = []

    for revision in script.walk_revisions():
        revision_id = revision.revision or ""
        if len(revision_id) > MAX_ALEMBIC_REVISION_LEN:
            offenders.append((revision_id, revision.path))

    if offenders:
        details = ", ".join(f"{revision_id} ({path})" for revision_id, path in offenders)
        raise RuntimeError(
            f"Alembic revision ids must be <= {MAX_ALEMBIC_REVISION_LEN} characters. "
            f"Found invalid revisions: {details}"
        )


def run_migrations_offline() -> None:
    validate_revision_id_lengths()
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    validate_revision_id_lengths()
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args={"statement_cache_size": 0},
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
