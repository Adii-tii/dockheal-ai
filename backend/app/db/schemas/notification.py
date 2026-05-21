"""
Pydantic v2 schemas — Notification domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import NotificationStatus


class _NotificationBase(BaseModel):
    investigation_id: uuid.UUID | None = None
    notification_type: str = Field(
        ..., max_length=100,
        examples=["SLACK", "EMAIL", "PAGERDUTY", "WEBHOOK",
                  "SMS", "TEAMS", "OPSGENIE", "CUSTOM"],
    )
    recipient: str = Field(
        ..., max_length=512,
        description=(
            "Channel-specific destination: #slack-channel, user@example.com, "
            "PagerDuty routing key, webhook URL, etc."
        ),
    )
    status: NotificationStatus = NotificationStatus.PENDING
    sent_at: datetime | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")


class NotificationCreate(_NotificationBase):
    """Body for creating a new notification record."""
    pass


class NotificationUpdate(BaseModel):
    """Partial update — typically called by the delivery worker."""
    status: NotificationStatus | None = None
    sent_at: datetime | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")


class NotificationResponse(_NotificationBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    created_at: datetime
