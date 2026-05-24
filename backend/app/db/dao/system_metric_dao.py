"""
DAO — SystemMetric repository.
"""

from datetime import datetime, timezone, timedelta
from typing import Sequence

from sqlalchemy import and_, select, func, delete, insert, text
import uuid

from app.db.dao.base_dao import BaseDAO
from app.db.models.system_metric import SystemMetric
from app.db.models.system_metrics_hourly import SystemMetricHourly


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

    async def archive_old_metrics(self, retention_hours: int = 24) -> int:
        """
        Downsample metrics older than `retention_hours` by calculating hourly averages per container.
        Insert aggregated rows into system_metrics_hourly, then delete raw records.
        Returns the number of raw records deleted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=retention_hours)

        hour_bucket_expr = func.date_trunc(text("'hour'"), SystemMetric.created_at)
        # 1. Fetch aggregated metrics
        stmt = (
            select(
                SystemMetric.container_id,
                hour_bucket_expr.label("hour_bucket"),
                func.avg(SystemMetric.cpu_usage).label("cpu_avg"),
                func.avg(SystemMetric.memory_usage).label("memory_avg"),
                func.avg(SystemMetric.disk_usage).label("disk_avg"),
                func.avg(SystemMetric.network_usage).label("network_avg"),
                func.max(SystemMetric.anomaly_score).label("anomaly_max"),
            )
            .where(SystemMetric.created_at < cutoff)
            .group_by(SystemMetric.container_id, hour_bucket_expr)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return 0

        # 2. Insert into system_metrics_hourly
        hourly_records = []
        for r in rows:
            hourly_records.append({
                "id": uuid.uuid4(),
                "container_id": r.container_id,
                "created_at": r.hour_bucket,
                "cpu_usage_avg": r.cpu_avg,
                "memory_usage_avg": r.memory_avg,
                "disk_usage_avg": r.disk_avg,
                "network_usage_avg": r.network_avg,
                "anomaly_score_max": r.anomaly_max,
            })

        # Bulk insert
        await self.session.execute(
            insert(SystemMetricHourly),
            hourly_records
        )

        # 3. Delete old raw metrics
        del_stmt = delete(SystemMetric).where(SystemMetric.created_at < cutoff)
        del_result = await self.session.execute(del_stmt)
        deleted_count = del_result.rowcount

        return deleted_count
