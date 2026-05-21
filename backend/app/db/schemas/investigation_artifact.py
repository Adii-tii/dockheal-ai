"""
Pydantic v2 schemas — InvestigationArtifact domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _ArtifactBase(BaseModel):
    investigation_id: uuid.UUID
    artifact_type: str = Field(
        ..., max_length=100,
        examples=["log_snapshot", "stack_trace", "screenshot",
                  "sandbox_output", "ai_reasoning_dump", "metric_export",
                  "config_diff", "custom"],
    )
    artifact_name: str = Field(..., max_length=512)
    storage_path: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")


class ArtifactCreate(_ArtifactBase):
    """Body for registering a new artifact."""
    pass


class ArtifactUpdate(BaseModel):
    """Partial update — e.g. backfill storage_path after upload completes."""
    storage_path: str | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")


class ArtifactResponse(_ArtifactBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    created_at: datetime
