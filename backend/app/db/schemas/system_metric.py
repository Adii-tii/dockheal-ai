"""
Pydantic v2 schemas — SystemMetric domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SystemMetricCreate(BaseModel):
    container_id: uuid.UUID
    cpu_usage: float | None = Field(None, ge=0.0, le=100.0)
    memory_usage: float | None = Field(None, ge=0.0, le=100.0)
    disk_usage: float | None = Field(None, ge=0.0, le=100.0)
    network_usage: float | None = Field(None, ge=0.0)
    anomaly_score: float | None = Field(None, ge=0.0, le=1.0)
    raw_metrics: dict[str, Any] | None = None
    anomaly_metadata: dict[str, Any] | None = None


class SystemMetricResponse(SystemMetricCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
