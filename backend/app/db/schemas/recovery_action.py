"""
Pydantic v2 schemas — RecoveryAction domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ExecutionStatus


class _RecoveryActionBase(BaseModel):
    investigation_id: uuid.UUID
    action_name: str = Field(..., max_length=255)
    action_type: str = Field(..., max_length=100)
    execution_status: ExecutionStatus = ExecutionStatus.PENDING
    execution_logs: str | None = None
    rollback_available: bool = False
    rollback_executed: bool = False
    rollback_status: str | None = Field(None, max_length=100)
    correlation_id: str | None = Field(None, max_length=255)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parameters: dict[str, Any] | None = None
    validation_results: dict[str, Any] | None = None
    rollback_metadata: dict[str, Any] | None = None


class RecoveryActionCreate(_RecoveryActionBase):
    pass


class RecoveryActionUpdate(BaseModel):
    execution_status: ExecutionStatus | None = None
    execution_logs: str | None = None
    rollback_available: bool | None = None
    rollback_executed: bool | None = None
    rollback_status: str | None = Field(None, max_length=100)
    correlation_id: str | None = Field(None, max_length=255)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    parameters: dict[str, Any] | None = None
    validation_results: dict[str, Any] | None = None
    rollback_metadata: dict[str, Any] | None = None


class RecoveryActionResponse(_RecoveryActionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
