"""
Pydantic v2 schemas — Investigation domain.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import LifecycleState, RecoveryStatus, SeverityLevel


class _InvestigationBase(BaseModel):
    container_id: uuid.UUID
    title: str = Field(..., max_length=512)
    incident_summary: str | None = None
    severity_level: SeverityLevel = SeverityLevel.P2
    lifecycle_state: LifecycleState = LifecycleState.DETECTED
    status: str | None = None
    root_cause: str | None = None
    proposed_action: str | None = None
    auto_restart_allowed: bool = False
    approval_required: bool = True
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence_found: list[Any] | None = None
    contributing_factors: list[Any] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    # ── New fields ─────────────────────────────────────────────────────────────
    ai_reasoning_summary: str | None = None
    decision_trace: dict[str, Any] = {}
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    detected_signals: list[Any] = []
    correlation_id: str | None = Field(None, max_length=255)
    version: int = 1
    created_by: str = "monitor_worker"
    # ── New operational fields ─────────────────────────────────────────────────
    current_step: str | None = Field(
        None, max_length=255,
        description="Live label of the AI’s active action step"
    )
    recovery_status: RecoveryStatus = Field(
        RecoveryStatus.UNKNOWN,
        description="Permanence of the fix: TEMPORARY / PERMANENT / PARTIAL / UNKNOWN"
    )
    approval_timeout_at: datetime | None = Field(
        None,
        description="Hard deadline for human approval; auto-rejects when exceeded"
    )
    is_auto_recovery: bool = Field(
        False,
        description="True when remediation was applied without a human approval step"
    )
    incident_hash: str | None = Field(
        None, max_length=64,
        description="SHA-256 fingerprint used to deduplicate repeated incidents"
    )


class InvestigationCreate(_InvestigationBase):
    """Body for opening a new investigation."""
    pass


class InvestigationUpdate(BaseModel):
    """Partial update — all fields optional."""
    title: str | None = Field(None, max_length=512)
    incident_summary: str | None = None
    severity_level: SeverityLevel | None = None
    lifecycle_state: LifecycleState | None = None
    status: str | None = None
    root_cause: str | None = None
    proposed_action: str | None = None
    auto_restart_allowed: bool | None = None
    approval_required: bool | None = None
    approved_by: str | None = None
    approved_at: datetime | None = None
    rejected_reason: str | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence_found: list[Any] | None = None
    contributing_factors: list[Any] | None = None
    metadata_: dict[str, Any] | None = Field(None, alias="metadata")
    # ── New fields ─────────────────────────────────────────────────────────────
    ai_reasoning_summary: str | None = None
    decision_trace: dict[str, Any] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    detected_signals: list[Any] | None = None
    correlation_id: str | None = Field(None, max_length=255)
    version: int | None = None
    created_by: str | None = None
    # ── New operational fields ─────────────────────────────────────────────────
    current_step: str | None = Field(None, max_length=255)
    recovery_status: RecoveryStatus | None = None
    approval_timeout_at: datetime | None = None
    is_auto_recovery: bool | None = None
    incident_hash: str | None = Field(None, max_length=64)


class InvestigationResponse(_InvestigationBase):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class InvestigationSummary(BaseModel):
    """Lightweight list view — omits heavy JSONB fields."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    container_id: uuid.UUID
    title: str
    severity_level: SeverityLevel
    lifecycle_state: LifecycleState
    confidence: float | None
    current_step: str | None
    recovery_status: RecoveryStatus
    is_auto_recovery: bool
    incident_hash: str | None
    started_at: datetime | None
    resolved_at: datetime | None
    approval_timeout_at: datetime | None
    created_at: datetime
