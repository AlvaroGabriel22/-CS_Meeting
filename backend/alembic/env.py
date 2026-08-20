"""Alembic environment — the URL always comes from app settings."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from app.core.config import get_settings
from app.db.base import Base, engine
from app.db import models  # noqa: F401  (imported for its side effect: metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", get_settings().sqlalchemy_url)


def run_migrations_offline() -> None:
    context.configure(
        url=get_settings().sqlalchemy_url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # SQLite needs table rebuilds for ALTER
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
