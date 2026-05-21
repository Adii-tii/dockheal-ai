"""
ORM model — containers table.

Tracks every Docker container/service that DockHeal monitors.
JSONB columns store runtime-variable data (labels, ports, runtime_metadata)
that changes across container restarts without requiring schema migrations.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin
from app.db.models.enums import ContainerStatus, HealthStatus
from sqlalchemy import Enum as SAEnum


class Container(Base, TimestampMixin):
    """Monitored container / Docker service."""

    __tablename__ = "containers"

    # ── Core identity ──────────────────────────────────────────────────────
    container_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    image_name: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # ── Runtime state ──────────────────────────────────────────────────────
    status: Mapped[ContainerStatus] = mapped_column(
        SAEnum(ContainerStatus, name="container_status_enum", create_type=False),
        nullable=False,
        default=ContainerStatus.UNKNOWN,
        index=True,
    )
    health_status: Mapped[HealthStatus] = mapped_column(
        SAEnum(HealthStatus, name="health_status_enum", create_type=False),
        nullable=False,
        default=HealthStatus.NONE,
    )

    # ── Policy ────────────────────────────────────────────────────────────
    auto_restart: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    environment: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="e.g. production, staging, dev"
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── JSONB ─────────────────────────────────────────────────────────────
    labels: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Docker labels key/value map"
    )
    ports: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Exposed port bindings"
    )
    runtime_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Engine-specific info (cgroup, network mode, etc.)"
    )

    # ── Relationships ─────────────────────────────────────────────────────
    investigations: Mapped[list["Investigation"]] = relationship(  # noqa: F821
        "Investigation",
        back_populates="container",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    system_metrics: Mapped[list["SystemMetric"]] = relationship(  # noqa: F821
        "SystemMetric",
        back_populates="container",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ── Composite indexes ─────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_containers_status_last_seen", "status", "last_seen"),
    )

    def __repr__(self) -> str:
        return f"<Container id={self.id} name={self.container_name!r} status={self.status}>"
