"""
DockHeal — SQLAlchemy declarative base and shared mixins.

All ORM models inherit from `Base`.  Tables that need automatic UUID primary
keys and audit timestamps should also inherit from `TimestampMixin`.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Return timezone-aware UTC now (used for Python-side defaults)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """
    Single declarative base for the entire DockHeal schema.

    All models that import from this module will be registered here and
    picked up by Alembic's autogenerate.
    """
    pass


class UUIDMixin:
    """UUID v4 primary key — stored as native PostgreSQL UUID type."""
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin(UUIDMixin):
    """
    Adds `created_at` and `updated_at` to any model.

    * `created_at` is set once by the DB server on INSERT.
    * `updated_at` is updated automatically by the DB server on every UPDATE
      via `onupdate=func.now()`.
    """
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
