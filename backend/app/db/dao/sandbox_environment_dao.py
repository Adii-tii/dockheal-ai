"""
DAO — SandboxEnvironment repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.sandbox_environment import SandboxEnvironment
from app.db.models.enums import SandboxStatus


class SandboxEnvironmentDAO(BaseDAO[SandboxEnvironment]):
    model = SandboxEnvironment

    async def get_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> Sequence[SandboxEnvironment]:
        result = await self.session.execute(
            select(SandboxEnvironment)
            .where(SandboxEnvironment.investigation_id == investigation_id)
            .order_by(SandboxEnvironment.created_at.desc())
        )
        return result.scalars().all()

    async def get_running(self) -> Sequence[SandboxEnvironment]:
        """Return all currently running sandbox environments."""
        result = await self.session.execute(
            select(SandboxEnvironment)
            .where(SandboxEnvironment.status == SandboxStatus.RUNNING)
        )
        return result.scalars().all()

    async def get_active_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> SandboxEnvironment | None:
        result = await self.session.execute(
            select(SandboxEnvironment)
            .where(
                SandboxEnvironment.investigation_id == investigation_id,
                SandboxEnvironment.status.in_(
                    [SandboxStatus.PENDING, SandboxStatus.RUNNING]
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()
