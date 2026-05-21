"""
Pydantic v2 schemas — SandboxEnvironment domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import SandboxStatus


class _SandboxBase(BaseModel):
    investigation_id: uuid.UUID
    environment_name: str
    status: SandboxStatus = SandboxStatus.PENDING
    purpose: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cloned_resources: list[Any] | None = None
    findings: list[Any] | None = None
    actions_tested: list[Any] | None = None
    validation_results: dict[str, Any] | None = None


class SandboxEnvironmentCreate(_SandboxBase):
    pass


class SandboxEnvironmentUpdate(BaseModel):
    status: SandboxStatus | None = None
    purpose: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    cloned_resources: list[Any] | None = None
    findings: list[Any] | None = None
    actions_tested: list[Any] | None = None
    validation_results: dict[str, Any] | None = None


class SandboxEnvironmentResponse(_SandboxBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
