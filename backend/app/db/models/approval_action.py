"""
ORM model — approval_actions table.

Immutable audit trail of every human APPROVE / REJECT decision.
Multiple entries can exist per investigation (e.g., initial reject,
then re-submission and approve).
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin
from app.db.models.enums import ActionType
from sqlalchemy import Enum as SAEnum


class ApprovalAction(Base, UUIDMixin):
    """Human approval or rejection of an AI-proposed remediation."""

    __tablename__ = "approval_actions"

    # ── Foreign key ────────────────────────────────────────────────────────
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Decision ───────────────────────────────────────────────────────────
    action_type: Mapped[ActionType] = mapped_column(
        SAEnum(ActionType, name="action_type_enum", create_type=False),
        nullable=False,
    )
    approved_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="e.g. WEB_UI, API, SLACK_BOT"
    )

    # ── Immutable timestamp ────────────────────────────────────────────────
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation"] = relationship(  # noqa: F821
        "Investigation", back_populates="approval_actions"
    )

    __table_args__ = (
        Index("ix_approval_inv_created", "investigation_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<ApprovalAction id={self.id} type={self.action_type} "
            f"by={self.approved_by!r}>"
        )
