"""
ORM model — system_metrics_hourly table.

Stores hourly downsampled metrics for historical tracking and visualization,
preventing unbounded database growth in the raw system_metrics table.
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, UUIDMixin


class SystemMetricHourly(Base, UUIDMixin):
    """Hourly aggregated container metrics snapshot for historical retention."""

    __tablename__ = "system_metrics_hourly"

    # ── Foreign key ────────────────────────────────────────────────────────
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Downsampled scalar metrics ─────────────────────────────────────────
    cpu_usage_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Average CPU usage % over the hour"
    )
    memory_usage_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Average Memory usage % over the hour"
    )
    disk_usage_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Average Disk usage % over the hour"
    )
    network_usage_avg: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Average Network bytes/sec over the hour"
    )
    anomaly_score_max: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="Maximum anomaly score observed during the hour"
    )

    # ── Timestamp (marks the hour boundary) ────────────────────────────────
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    container: Mapped["Container"] = relationship(  # noqa: F821
        "Container",
        foreign_keys=[container_id],
    )

    __table_args__ = (
        Index(
            "ix_metrics_hourly_container_created",
            "container_id",
            "created_at",
        ),
        Index(
            "ix_metrics_hourly_created_at",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemMetricHourly id={self.id} container={self.container_id} "
            f"created_at={self.created_at}>"
        )
