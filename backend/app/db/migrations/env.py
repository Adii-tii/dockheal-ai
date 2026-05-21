"""
Alembic environment script for DockHeal.

Supports async migrations via asyncpg using run_async_migrations().
The DATABASE_URL is read from the environment (via .env) so it is never
hard-coded in source control.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()

# ── Alembic config object ──────────────────────────────────────────────────────
config = context.config

# Inject async DSN into alembic config so it doesn't have to live in alembic.ini
_raw_url = os.getenv("DATABASE_URL", "")
if not _raw_url:
    import urllib.parse
    _pw  = urllib.parse.quote_plus(os.getenv("PG_PASSWORD", ""))
    _h   = os.getenv("PG_HOST", "localhost")
    _p   = os.getenv("PG_PORT", "5432")
    _u   = urllib.parse.quote_plus(os.getenv("PG_USER", "postgres"))
    _db  = os.getenv("PG_DB", "dockheal")
    _raw_url = f"postgresql+asyncpg://{_u}:{_pw}@{_h}:{_p}/{_db}"
else:
    _raw_url = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)

config.set_main_option("sqlalchemy.url", _raw_url.replace("%", "%%"))

# ── Python logging ─────────────────────────────────────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Import ALL models so Alembic sees the metadata ────────────────────────────
# This import must happen AFTER load_dotenv() and before target_metadata is set.
from app.db.models import Base  # noqa: E402  (import after env setup)
from app.db.models import (     # noqa: F401  (side-effect: register tables)
    Container,
    Investigation,
    InvestigationTimelineEvent,
    RCAReport,
    ApprovalAction,
    SandboxEnvironment,
    RecoveryAction,
    SystemMetric,
)

target_metadata = Base.metadata


# ── Offline migrations (generate SQL script, no live DB) ──────────────────────

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online async migrations ────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ────────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
