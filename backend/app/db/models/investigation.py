"""
ORM model — investigations table.

Central table of the DockHeal schema.  Every AI-driven incident investigation
has exactly one row here.  Child tables (timeline events, RCA reports, approvals,
sandboxes, recovery actions) all FK back to this table.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models.base import Base, TimestampMixin
from app.db.models.enums import LifecycleState, RecoveryStatus, SeverityLevel
from sqlalchemy import Enum as SAEnum


class Investigation(Base, TimestampMixin):
    """
    Full lifecycle record for one AI investigation.

    Lifecycle state machine (see enums.LifecycleState):
        INITIATED → ANALYZING → AWAITING_APPROVAL → REMEDIATING → RESOLVED
                                                               ↘ REJECTED
                              ↘ ESCALATED
                ↘ BLOCKED
    """

    __tablename__ = "investigations"

    # ── Foreign key ────────────────────────────────────────────────────────
    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity / description ─────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    incident_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Classification ─────────────────────────────────────────────────────
    severity_level: Mapped[SeverityLevel] = mapped_column(
        SAEnum(SeverityLevel, name="severity_level_enum", create_type=False),
        nullable=False,
        default=SeverityLevel.P2,
        index=True,
    )
    lifecycle_state: Mapped[LifecycleState] = mapped_column(
        SAEnum(LifecycleState, name="lifecycle_state_enum", create_type=False),
        nullable=False,
        default=LifecycleState.INITIATED,
        index=True,
    )

    # ── AI outputs ─────────────────────────────────────────────────────────
    ai_confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, comment="0.0 – 1.0"
    )
    status: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Human-readable status message shown in UI"
    )
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Policy flags ───────────────────────────────────────────────────────
    auto_restart_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    # ── Approval tracking ──────────────────────────────────────────────────
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Lifecycle timestamps ───────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Operational visibility & deduplication ────────────────────────────
    current_step: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Live label of the AI's current action, e.g. 'Running log analysis'"
    )
    recovery_status: Mapped[RecoveryStatus] = mapped_column(
        SAEnum(RecoveryStatus, name="recovery_status_enum", create_type=False),
        nullable=False,
        default=RecoveryStatus.UNKNOWN,
        comment="Permanence of the applied fix: TEMPORARY / PERMANENT / PARTIAL / UNKNOWN"
    )
    approval_timeout_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Deadline by which a human must approve; auto-rejects when exceeded"
    )
    is_auto_recovery: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        comment="True when the fix was applied automatically without human approval"
    )
    incident_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True,
        comment="SHA-256 fingerprint of (container_id, root_cause_signature) for deduplication"
    )

    # ── JSONB (AI reasoning & evidence) ───────────────────────────────────
    ai_reasoning: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Full chain-of-thought from the AI investigator"
    )
    evidence_found: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Structured evidence artifacts collected during analysis"
    )
    contributing_factors: Mapped[list[Any] | None] = mapped_column(
        JSONB, nullable=True, default=list,
        comment="Secondary contributing factors identified"
    )
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB, nullable=True, default=dict,
        comment="Arbitrary extra metadata (version tags, trace IDs, etc.)"
    )

    # ── Relationships ──────────────────────────────────────────────────────
    container: Mapped["Container"] = relationship(  # noqa: F821
        "Container", back_populates="investigations"
    )
    timeline_events: Mapped[list["InvestigationTimelineEvent"]] = relationship(  # noqa: F821
        "InvestigationTimelineEvent",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InvestigationTimelineEvent.created_at",
    )
    rca_reports: Mapped[list["RCAReport"]] = relationship(  # noqa: F821
        "RCAReport",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    approval_actions: Mapped[list["ApprovalAction"]] = relationship(  # noqa: F821
        "ApprovalAction",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    sandbox_environments: Mapped[list["SandboxEnvironment"]] = relationship(  # noqa: F821
        "SandboxEnvironment",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    recovery_actions: Mapped[list["RecoveryAction"]] = relationship(  # noqa: F821
        "RecoveryAction",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    artifacts: Mapped[list["InvestigationArtifact"]] = relationship(  # noqa: F821
        "InvestigationArtifact",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InvestigationArtifact.created_at",
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification",
        back_populates="investigation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Notification.created_at",
    )

    # ── Composite indexes ──────────────────────────────────────────────────
    __table_args__ = (
        Index(
            "ix_investigations_state_severity",
            "lifecycle_state",
            "severity_level",
        ),
        Index(
            "ix_investigations_container_state",
            "container_id",
            "lifecycle_state",
        ),
        Index("ix_investigations_created_at", "created_at"),
        Index("ix_investigations_incident_hash", "incident_hash"),
    )

    def __repr__(self) -> str:
        return (
            f"<Investigation id={self.id} state={self.lifecycle_state} "
            f"severity={self.severity_level}>"
        )
