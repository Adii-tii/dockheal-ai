"""
ORM model — recovery_actions table.

Tracks every remediation execution attempt.  Supports rollback metadata so
that a failed or unwanted action can be reversed.
"""

import uuid
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin
from app.db.models.enums import ExecutionStatus
from sqlalchemy import Enum as SAEnum


class RecoveryAction(Base, UUIDMixin):
    """Single remediation action execution record."""

    __tablename__ = "recovery_actions"

    # ── Foreign key ────────────────────────────────────────────────────────
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Action identity ────────────────────────────────────────────────────
    action_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Human-readable name, e.g. 'restart_container'"
    )
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Category: RESTART, CONFIG_PATCH, SCALE, ROLLBACK, CUSTOM"
    )

    # ── Execution state ────────────────────────────────────────────────────
    execution_status: Mapped[ExecutionStatus] = mapped_column(
        SAEnum(ExecutionStatus, name="execution_status_enum", create_type=False),
        nullable=False,
        default=ExecutionStatus.PENDING,
        index=True,
    )
    execution_logs: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Raw stdout/stderr captured during execution"
    )
    rollback_available: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    rollback_executed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    rollback_status: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # ── Lifecycle timestamps ───────────────────────────────────────────────
    started_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB ──────────────────────────────────────────────────────────────
    parameters: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Input parameters passed to the action executor"
    )
    validation_results: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Health-check / assertion results after execution"
    )
    rollback_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Snapshot required to undo this action"
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation"] = relationship(  # noqa: F821
        "Investigation", back_populates="recovery_actions"
    )

    __table_args__ = (
        Index(
            "ix_recovery_inv_status",
            "investigation_id",
            "execution_status",
        ),
        Index("ix_recovery_created_at", "created_at"),
        Index(
            "ix_recovery_inv_created",
            "investigation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryAction id={self.id} name={self.action_name!r} "
            f"status={self.execution_status}>"
        )
