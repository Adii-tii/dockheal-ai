"""
DAO — RecoveryAction repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.recovery_action import RecoveryAction
from app.db.models.enums import ExecutionStatus


class RecoveryActionDAO(BaseDAO[RecoveryAction]):
    model = RecoveryAction

    async def get_for_investigation(
        self,
        investigation_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[RecoveryAction]:
        result = await self.session.execute(
            select(RecoveryAction)
            .where(RecoveryAction.investigation_id == investigation_id)
            .order_by(RecoveryAction.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_status(
        self,
        investigation_id: uuid.UUID,
        status: ExecutionStatus,
    ) -> Sequence[RecoveryAction]:
        result = await self.session.execute(
            select(RecoveryAction)
            .where(
                RecoveryAction.investigation_id == investigation_id,
                RecoveryAction.execution_status == status,
            )
        )
        return result.scalars().all()

    async def get_rollback_candidates(
        self, investigation_id: uuid.UUID
    ) -> Sequence[RecoveryAction]:
        """Return successful actions that support rollback."""
        result = await self.session.execute(
            select(RecoveryAction)
            .where(
                RecoveryAction.investigation_id == investigation_id,
                RecoveryAction.rollback_available.is_(True),
                RecoveryAction.execution_status == ExecutionStatus.SUCCESS,
            )
            .order_by(RecoveryAction.completed_at.desc())
        )
        return result.scalars().all()
