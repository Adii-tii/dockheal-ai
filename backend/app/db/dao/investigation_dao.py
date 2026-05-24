"""
DAO — Investigation repository.

Contains lifecycle-aware queries for the core investigations table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import and_, select

from app.db.dao.base_dao import BaseDAO
from app.db.models.investigation import Investigation
from app.db.models.enums import LifecycleState, SeverityLevel


# States that represent an active (non-terminal) investigation
ACTIVE_STATES: tuple[LifecycleState, ...] = (
    LifecycleState.DETECTED,
    LifecycleState.INVESTIGATING,
    LifecycleState.RCA_IDENTIFIED,
    LifecycleState.AWAITING_APPROVAL,
    LifecycleState.RECOVERING,
    LifecycleState.VALIDATING,
    LifecycleState.MONITORING,
    LifecycleState.PAUSED,
)

TERMINAL_STATES: tuple[LifecycleState, ...] = (
    LifecycleState.RESOLVED,
    LifecycleState.REJECTED,
    LifecycleState.TIMED_OUT,
    LifecycleState.ESCALATED,
)


class InvestigationDAO(BaseDAO[Investigation]):
    model = Investigation

    # ------------------------------------------------------------------
    # Container-scoped queries
    # ------------------------------------------------------------------

    async def get_by_container(
        self,
        container_id: uuid.UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[Investigation]:
        result = await self.session.execute(
            select(Investigation)
            .where(Investigation.container_id == container_id)
            .order_by(Investigation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_active_for_container(
        self, container_id: uuid.UUID
    ) -> Investigation | None:
        """Return the most recent non-terminal investigation for a container."""
        result = await self.session.execute(
            select(Investigation)
            .where(
                and_(
                    Investigation.container_id == container_id,
                    Investigation.lifecycle_state.in_(ACTIVE_STATES),
                )
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Lifecycle queries
    # ------------------------------------------------------------------

    async def get_by_state(
        self,
        state: LifecycleState,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Investigation]:
        result = await self.session.execute(
            select(Investigation)
            .where(Investigation.lifecycle_state == state)
            .order_by(Investigation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_awaiting_approval(self) -> Sequence[Investigation]:
        return await self.get_by_state(LifecycleState.AWAITING_APPROVAL)

    async def get_by_severity(
        self,
        severity: SeverityLevel,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Investigation]:
        result = await self.session.execute(
            select(Investigation)
            .where(Investigation.severity_level == severity)
            .order_by(Investigation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_active(self, *, limit: int = 100) -> Sequence[Investigation]:
        """Return all non-terminal investigations."""
        result = await self.session.execute(
            select(Investigation)
            .where(Investigation.lifecycle_state.in_(ACTIVE_STATES))
            .order_by(Investigation.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_resolved(
        self, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Investigation]:
        result = await self.session.execute(
            select(Investigation)
            .where(Investigation.lifecycle_state == LifecycleState.RESOLVED)
            .order_by(Investigation.resolved_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    # ------------------------------------------------------------------
    # State transitions (convenience helpers)
    # ------------------------------------------------------------------

    async def transition_state(
        self,
        investigation_id: uuid.UUID,
        new_state: LifecycleState,
        **extra_fields: object,
    ) -> Investigation | None:
        """
        Atomically update lifecycle_state plus any extra scalar fields.

        Extra fields allow callers to set e.g. `resolved_at`, `approved_by`
        in the same database round-trip.
        """
        return await self.update_by_id(
            investigation_id,
            lifecycle_state=new_state,
            **extra_fields,
        )

    # ------------------------------------------------------------------
    # New-field helpers
    # ------------------------------------------------------------------

    async def find_by_hash(
        self, incident_hash: str
    ) -> Investigation | None:
        """
        Deduplicate: return an existing active investigation with the same
        incident_hash, or None if this is a genuinely new incident.
        """
        result = await self.session.execute(
            select(Investigation)
            .where(
                Investigation.incident_hash == incident_hash,
                Investigation.lifecycle_state.in_(ACTIVE_STATES),
            )
            .order_by(Investigation.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_timed_out_approvals(
        self, now: datetime | None = None
    ) -> Sequence[Investigation]:
        """
        Return all investigations that are still AWAITING_APPROVAL but whose
        `approval_timeout_at` has passed.  Call this from a background task
        to auto-reject zombie approvals.
        """
        cutoff = now or datetime.now(timezone.utc)
        result = await self.session.execute(
            select(Investigation)
            .where(
                Investigation.lifecycle_state == LifecycleState.AWAITING_APPROVAL,
                Investigation.approval_timeout_at.isnot(None),
                Investigation.approval_timeout_at <= cutoff,
            )
        )
        return result.scalars().all()

    async def set_current_step(
        self,
        investigation_id: uuid.UUID,
        step_label: str,
    ) -> Investigation | None:
        """
        Lightweight single-field update for live AI action visibility.
        Called frequently during analysis — avoids loading the full row.
        """
        return await self.update_by_id(
            investigation_id, current_step=step_label
        )
