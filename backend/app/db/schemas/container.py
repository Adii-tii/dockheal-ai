"""
Pydantic v2 schemas — Container domain.

Three schema variants per domain:
  * Create  — request body for POST
  * Update  — request body for PUT/PATCH (all fields optional)
  * Response — what the API returns (includes DB-generated fields)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import ContainerStatus, HealthStatus


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

class _ContainerBase(BaseModel):
    container_name: str = Field(..., max_length=255)
    runtime_id: str = Field(..., max_length=255)
    image_name: str | None = Field(None, max_length=512)
    status: ContainerStatus = ContainerStatus.UNKNOWN
    health_status: HealthStatus = HealthStatus.NONE
    auto_restart: bool = False
    environment: str | None = Field(None, max_length=100)
    last_seen: datetime | None = None
    labels: dict[str, Any] | None = None
    ports: list[Any] | None = None
    runtime_metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ContainerCreate(_ContainerBase):
    """Body for registering a new monitored container."""
    pass


class ContainerUpdate(BaseModel):
    """All fields optional for partial updates."""
    container_name: str | None = Field(None, max_length=255)
    runtime_id: str | None = Field(None, max_length=255)
    image_name: str | None = None
    status: ContainerStatus | None = None
    health_status: HealthStatus | None = None
    auto_restart: bool | None = None
    environment: str | None = None
    last_seen: datetime | None = None
    labels: dict[str, Any] | None = None
    ports: list[Any] | None = None
    runtime_metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class ContainerResponse(_ContainerBase):
    """Full container record returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
