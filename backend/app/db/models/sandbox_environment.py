"""
ORM model — sandbox_environments table.

Represents one complete sandbox investigation environment spun up by the AI
to safely test remediation actions against a clone of the failing container.

Design note: individual cloned containers are NOT stored as separate rows;
the full environment snapshot lives in `cloned_resources` JSONB.
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin
from app.db.models.enums import SandboxStatus
from sqlalchemy import Enum as SAEnum


class SandboxEnvironment(Base, UUIDMixin):
    """Ephemeral sandbox environment for safe remediation testing."""

    __tablename__ = "sandbox_environments"

    # ── Foreign key ────────────────────────────────────────────────────────
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity ───────────────────────────────────────────────────────────
    environment_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    status: Mapped[SandboxStatus] = mapped_column(
        SAEnum(SandboxStatus, name="sandbox_status_enum", create_type=False),
        nullable=False,
        default=SandboxStatus.PENDING,
        index=True,
    )
    purpose: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="What the sandbox was created to test / validate"
    )

    # ── Lifecycle timestamps ───────────────────────────────────────────────
    started_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ended_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB (environment snapshot) ───────────────────────────────────────
    cloned_resources: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Full snapshot of cloned Docker resources"
    )
    findings: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Observations collected inside the sandbox"
    )
    actions_tested: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Remediation actions that were executed in the sandbox"
    )
    validation_results: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Pass/fail validation checks after sandbox actions"
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation"] = relationship(  # noqa: F821
        "Investigation", back_populates="sandbox_environments"
    )

    __table_args__ = (
        Index("ix_sandbox_inv_status", "investigation_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<SandboxEnvironment id={self.id} name={self.environment_name!r} "
            f"status={self.status}>"
        )
