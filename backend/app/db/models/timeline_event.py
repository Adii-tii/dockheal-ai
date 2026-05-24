"""
ORM model — investigation_timeline_events table.

Chronological event log for an investigation.  Every significant AI action,
human decision, or system event is appended here, enabling full replay of the
investigation timeline and post-mortem analysis.
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin
from app.db.models.enums import SeverityLevel, SourceType
from sqlalchemy import Enum as SAEnum


class InvestigationTimelineEvent(Base, UUIDMixin):
    """
    Append-only event log row.

    Design note: `updated_at` is intentionally absent — timeline events are
    immutable once written.  Use `created_at` for ordering.
    """

    __tablename__ = "investigation_timeline_events"

    # ── Foreign key ────────────────────────────────────────────────────────
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Event classification ───────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="e.g. ANALYSIS_STARTED, TOOL_CALLED, APPROVAL_REQUESTED, ACTION_EXECUTED"
    )
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type_enum", create_type=False),
        nullable=False,
        default=SourceType.AI_AGENT,
    )
    severity: Mapped[SeverityLevel | None] = mapped_column(
        SAEnum(SeverityLevel, name="severity_level_enum", create_type=False),
        nullable=True,
    )

    # ── Immutable timestamp ────────────────────────────────────────────────
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB payloads ─────────────────────────────────────────────────────
    raw_data: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Raw input that triggered this event"
    )
    tool_output: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Structured output from any AI tool call"
    )
    extra_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True, default=dict,
        comment="Additional metadata for replay / debugging"
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation"] = relationship(  # noqa: F821
        "Investigation", back_populates="timeline_events"
    )

    __table_args__ = (
        Index(
            "ix_timeline_inv_created",
            "investigation_id",
            "created_at",
        ),
        Index(
            "ix_timeline_inv_event_type",
            "investigation_id",
            "event_type",
        ),
        UniqueConstraint(
            "investigation_id",
            "sequence_number",
            name="uq_timeline_inv_sequence",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<TimelineEvent id={self.id} type={self.event_type!r} "
            f"inv={self.investigation_id}>"
        )
