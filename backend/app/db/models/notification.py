"""
ORM model — notifications table.

Outbound notification records for every alert sent to an external channel
(Slack, Email, PagerDuty, escalation systems, webhooks).

Design notes:
  * `notification_type` is a free-form string (not a PG enum) so new channel
    integrations don't require schema migrations.
  * `recipient` holds the channel-specific address/ID: Slack channel name,
    email address, PagerDuty routing key, webhook URL, etc.
  * JSONB `metadata_` stores channel-specific payloads, message IDs, retries,
    error messages, and any extra context.
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func, Enum as SAEnum

from app.db.models.base import Base, UUIDMixin
from app.db.models.enums import NotificationStatus


class Notification(Base, UUIDMixin):
    """Single outbound notification record."""

    __tablename__ = "notifications"

    # ── Foreign key (nullable — some notifications are system-wide) ────────
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="NULL for system-level notifications not tied to one investigation",
    )

    # ── Channel identity ───────────────────────────────────────────────────
    notification_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment=(
            "Channel type: SLACK | EMAIL | PAGERDUTY | WEBHOOK | "
            "SMS | TEAMS | OPSGENIE | CUSTOM"
        ),
    )
    recipient: Mapped[str] = mapped_column(
        String(512), nullable=False,
        comment=(
            "Channel-specific destination: Slack channel (#incidents), "
            "email address, PagerDuty routing key, webhook URL, etc."
        ),
    )

    # ── Delivery state ─────────────────────────────────────────────────────
    status: Mapped[NotificationStatus] = mapped_column(
        SAEnum(NotificationStatus, name="notification_status_enum", create_type=False),
        nullable=False,
        default=NotificationStatus.PENDING,
        index=True,
    )
    correlation_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    # ── Timestamp ──────────────────────────────────────────────────────────
    sent_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When the notification was successfully delivered"
    )
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB — channel-specific payload & delivery metadata ──────────────
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB, nullable=True, default=dict,
        comment=(
            "Flexible payload: message body, thread_ts, message_id, "
            "retry_count, error_message, escalation_level, etc."
        ),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation | None"] = relationship(  # noqa: F821
        "Investigation", back_populates="notifications"
    )

    # ── Indexes ────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_notifications_inv_status", "investigation_id", "status"),
        Index("ix_notifications_type_status", "notification_type", "status"),
        Index("ix_notifications_created_at", "created_at"),
        # GIN index for rich JSONB query support
        # e.g.  WHERE metadata @> '{"escalation_level": 2}'
        Index(
            "idx_notifications_metadata_gin",
            "metadata",
            postgresql_using="gin",
        ),
        Index(
            "ix_notifications_inv_created",
            "investigation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} type={self.notification_type!r} "
            f"recipient={self.recipient!r} status={self.status}>"
        )
