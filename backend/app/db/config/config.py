"""
DockHeal — async SQLAlchemy engine and session factory.

Replaces the raw psycopg2 connection with a fully async setup powered by:
  - SQLAlchemy 2.x async engine
  - asyncpg driver
  - Connection pooling (QueuePool, tuned for FastAPI)

Environment variables (via .env):
  DATABASE_URL   — full async DSN, e.g.
                   postgresql+asyncpg://postgres:secret@localhost:5432/dockheal
  PG_PASSWORD    — fallback if DATABASE_URL is not set (legacy support)
"""

import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

load_dotenv()

# ── Build the DSN ──────────────────────────────────────────────────────────────

def _build_database_url() -> str:
    """
    Prefer the explicit DATABASE_URL env var.
    Fall back to assembling one from individual PG_* vars for backwards
    compatibility with the existing .env file.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        # Alembic / psycopg2 style URLs may use 'postgresql://' — normalise.
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)

    import urllib.parse
    host     = os.getenv("PG_HOST", "localhost")
    port     = os.getenv("PG_PORT", "5432")
    user     = urllib.parse.quote_plus(os.getenv("PG_USER", "postgres"))
    password = urllib.parse.quote_plus(os.getenv("PG_PASSWORD", ""))
    db       = os.getenv("PG_DB", "dockheal")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


DATABASE_URL: str = _build_database_url()

# ── Engine ─────────────────────────────────────────────────────────────────────

engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_ECHO", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,       # verify connections before use
    pool_recycle=3600,        # recycle idle connections every hour
)

# ── Session factory ────────────────────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # avoid lazy-load errors after commit
    autoflush=False,
    autocommit=False,
)


# ── Test / migration engine (NullPool — no pooling) ───────────────────────────

def create_test_engine(url: str | None = None):
    """
    Return a poolless engine suitable for Alembic migrations or unit tests.
    Using NullPool avoids shared connections across threads/processes.
    """
    return create_async_engine(
        url or DATABASE_URL,
        poolclass=NullPool,
        echo=True,
    )