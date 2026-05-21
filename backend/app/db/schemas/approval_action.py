"""
Pydantic v2 schemas — ApprovalAction domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ActionType


class ApprovalActionCreate(BaseModel):
    investigation_id: uuid.UUID
    action_type: ActionType
    approved_by: str = Field(..., max_length=255)
    reason: str | None = None
    source: str | None = Field(None, max_length=100)


class ApprovalActionResponse(ApprovalActionCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
