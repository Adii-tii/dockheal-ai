"""
Pydantic v2 schemas — SystemMetricHourly domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SystemMetricHourlyCreate(BaseModel):
    container_id: uuid.UUID
    cpu_usage_avg: float | None = Field(None, ge=0.0, le=100.0)
    memory_usage_avg: float | None = Field(None, ge=0.0, le=100.0)
    disk_usage_avg: float | None = Field(None, ge=0.0, le=100.0)
    network_usage_avg: float | None = Field(None, ge=0.0)
    anomaly_score_max: float | None = Field(None, ge=0.0, le=1.0)
    created_at: datetime


class SystemMetricHourlyResponse(SystemMetricHourlyCreate):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
