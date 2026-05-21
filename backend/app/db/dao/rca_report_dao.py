"""
DAO — RCAReport repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.rca_report import RCAReport


class RCAReportDAO(BaseDAO[RCAReport]):
    model = RCAReport

    async def get_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> Sequence[RCAReport]:
        """Return all RCA reports for an investigation, newest first."""
        result = await self.session.execute(
            select(RCAReport)
            .where(RCAReport.investigation_id == investigation_id)
            .order_by(RCAReport.rca_version.desc())
        )
        return result.scalars().all()

    async def get_latest(self, investigation_id: uuid.UUID) -> RCAReport | None:
        """Return the highest-version RCA report for an investigation."""
        result = await self.session.execute(
            select(RCAReport)
            .where(RCAReport.investigation_id == investigation_id)
            .order_by(RCAReport.rca_version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def next_version(self, investigation_id: uuid.UUID) -> int:
        """Compute the next rca_version number for an investigation."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.max(RCAReport.rca_version)).where(
                RCAReport.investigation_id == investigation_id
            )
        )
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1
