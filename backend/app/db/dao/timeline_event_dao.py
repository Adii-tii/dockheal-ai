"""
DAO — InvestigationTimelineEvent repository.

Append-only events; no update/delete exposed deliberately.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.timeline_event import InvestigationTimelineEvent
from app.db.models.enums import SourceType


class TimelineEventDAO(BaseDAO[InvestigationTimelineEvent]):
    model = InvestigationTimelineEvent

    async def get_for_investigation(
        self,
        investigation_id: uuid.UUID,
        *,
        limit: int = 500,
        offset: int = 0,
    ) -> Sequence[InvestigationTimelineEvent]:
        """Return all events for an investigation ordered chronologically."""
        result = await self.session.execute(
            select(InvestigationTimelineEvent)
            .where(
                InvestigationTimelineEvent.investigation_id == investigation_id
            )
            .order_by(InvestigationTimelineEvent.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_event_type(
        self,
        investigation_id: uuid.UUID,
        event_type: str,
    ) -> Sequence[InvestigationTimelineEvent]:
        result = await self.session.execute(
            select(InvestigationTimelineEvent)
            .where(
                InvestigationTimelineEvent.investigation_id == investigation_id,
                InvestigationTimelineEvent.event_type == event_type,
            )
            .order_by(InvestigationTimelineEvent.created_at.asc())
        )
        return result.scalars().all()

    async def get_by_source(
        self,
        investigation_id: uuid.UUID,
        source_type: SourceType,
    ) -> Sequence[InvestigationTimelineEvent]:
        result = await self.session.execute(
            select(InvestigationTimelineEvent)
            .where(
                InvestigationTimelineEvent.investigation_id == investigation_id,
                InvestigationTimelineEvent.source_type == source_type,
            )
            .order_by(InvestigationTimelineEvent.created_at.asc())
        )
        return result.scalars().all()

    async def count_for_investigation(self, investigation_id: uuid.UUID) -> int:
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count())
            .select_from(InvestigationTimelineEvent)
            .where(
                InvestigationTimelineEvent.investigation_id == investigation_id
            )
        )
        return result.scalar_one()
