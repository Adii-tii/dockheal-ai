"""
ORM model — system_metrics table.

Stores point-in-time anomaly snapshots for monitored containers.
Designed for high insert volume; kept lean with only scalar columns for
the core metrics and JSONB for raw/extended data.
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin


class SystemMetric(Base, UUIDMixin):
    """Point-in-time container metrics snapshot with anomaly scoring."""

    __tablename__ = "system_metrics"

    # ── Foreign key ────────────────────────────────────────────────────────
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Core scalar metrics ────────────────────────────────────────────────
    cpu_usage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="CPU usage % (0.0 – 100.0)"
    )
    memory_usage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Memory usage % (0.0 – 100.0)"
    )
    disk_usage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Disk usage % (0.0 – 100.0)"
    )
    network_usage: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Network bytes/sec (combined in+out)"
    )
    anomaly_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="AI anomaly score 0.0 (normal) – 1.0 (critical)"
    )

    # ── Immutable timestamp ────────────────────────────────────────────────
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB (extended data) ──────────────────────────────────────────────
    raw_metrics: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Full Docker stats payload"
    )
    anomaly_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Which signals triggered the anomaly score"
    )

    # ── Relationships ──────────────────────────────────────────────────────
    container: Mapped["Container"] = relationship(  # noqa: F821
        "Container", back_populates="system_metrics"
    )

    __table_args__ = (
        Index(
            "ix_metrics_container_created",
            "container_id",
            "created_at",
        ),
        Index(
            "ix_metrics_anomaly_score",
            "anomaly_score",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemMetric id={self.id} container={self.container_id} "
            f"anomaly={self.anomaly_score}>"
        )
