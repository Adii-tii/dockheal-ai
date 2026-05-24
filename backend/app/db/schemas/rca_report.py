"""
Pydantic v2 schemas — RCAReport domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _RCAReportBase(BaseModel):
    investigation_id: uuid.UUID
    rca_version: int = Field(1, ge=1)
    is_final: bool = False
    incident_summary: str | None = None
    impact_assessment: str | None = None
    what_failed: str | None = None
    why_it_happened: str | None = None
    action_proposed: str | None = None
    recovery_status: str | None = None
    long_term_prevention: str | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    ai_reasoning_summary: str | None = None
    evidence_found: list[Any] | None = None
    contributing_factors: list[Any] | None = None
    recommendations: list[Any] | None = None


class RCAReportCreate(_RCAReportBase):
    pass


class RCAReportUpdate(BaseModel):
    rca_version: int | None = Field(None, ge=1)
    is_final: bool | None = None
    incident_summary: str | None = None
    impact_assessment: str | None = None
    what_failed: str | None = None
    why_it_happened: str | None = None
    action_proposed: str | None = None
    recovery_status: str | None = None
    long_term_prevention: str | None = None
    confidence_score: float | None = Field(None, ge=0.0, le=1.0)
    ai_reasoning_summary: str | None = None
    evidence_found: list[Any] | None = None
    contributing_factors: list[Any] | None = None
    recommendations: list[Any] | None = None


class RCAReportResponse(_RCAReportBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
