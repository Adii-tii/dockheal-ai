"""
Pydantic v2 schemas — InvestigationTimelineEvent domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import SeverityLevel, SourceType


class _TimelineEventBase(BaseModel):
    investigation_id: uuid.UUID
    event_type: str = Field(..., max_length=100)
    sequence_number: int
    correlation_id: str | None = Field(None, max_length=255)
    title: str = Field(..., max_length=512)
    description: str | None = None
    source_type: SourceType = SourceType.AI_AGENT
    severity: SeverityLevel | None = None
    raw_data: dict[str, Any] | None = None
    tool_output: dict[str, Any] | None = None
    extra_context: dict[str, Any] | None = None


class TimelineEventCreate(_TimelineEventBase):
    """Body for appending a new timeline event."""
    pass


class TimelineEventResponse(_TimelineEventBase):
    """Full event record — `created_at` is immutable."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
