"""
DAO — SystemMetric repository.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import and_, select

from app.db.dao.base_dao import BaseDAO
from app.db.models.system_metric import SystemMetric


class SystemMetricDAO(BaseDAO[SystemMetric]):
    model = SystemMetric

    async def get_for_container(
        self,
        container_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[SystemMetric]:
        """Return metrics for a container, newest first."""
        result = await self.session.execute(
            select(SystemMetric)
            .where(SystemMetric.container_id == container_id)
            .order_by(SystemMetric.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_anomalous(
        self,
        container_id: uuid.UUID,
        *,
        threshold: float = 0.7,
        limit: int = 50,
    ) -> Sequence[SystemMetric]:
        """Return metric snapshots where anomaly_score >= threshold."""
        result = await self.session.execute(
            select(SystemMetric)
            .where(
                SystemMetric.container_id == container_id,
                SystemMetric.anomaly_score >= threshold,
            )
            .order_by(SystemMetric.anomaly_score.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_in_time_range(
        self,
        container_id: uuid.UUID,
        since: datetime,
        until: datetime | None = None,
        *,
        limit: int = 500,
    ) -> Sequence[SystemMetric]:
        conditions = [
            SystemMetric.container_id == container_id,
            SystemMetric.created_at >= since,
        ]
        if until:
            conditions.append(SystemMetric.created_at <= until)

        result = await self.session.execute(
            select(SystemMetric)
            .where(and_(*conditions))
            .order_by(SystemMetric.created_at.asc())
            .limit(limit)
        )
        return result.scalars().all()
