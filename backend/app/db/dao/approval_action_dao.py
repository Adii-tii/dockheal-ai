"""
DAO — ApprovalAction repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.approval_action import ApprovalAction
from app.db.models.enums import ActionType


class ApprovalActionDAO(BaseDAO[ApprovalAction]):
    model = ApprovalAction

    async def get_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> Sequence[ApprovalAction]:
        result = await self.session.execute(
            select(ApprovalAction)
            .where(ApprovalAction.investigation_id == investigation_id)
            .order_by(ApprovalAction.created_at.asc())
        )
        return result.scalars().all()

    async def get_latest_for_investigation(
        self, investigation_id: uuid.UUID
    ) -> ApprovalAction | None:
        """Return the most recent approval/rejection decision."""
        result = await self.session.execute(
            select(ApprovalAction)
            .where(ApprovalAction.investigation_id == investigation_id)
            .order_by(ApprovalAction.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_action_type(
        self,
        investigation_id: uuid.UUID,
        action_type: ActionType,
    ) -> Sequence[ApprovalAction]:
        result = await self.session.execute(
            select(ApprovalAction)
            .where(
                ApprovalAction.investigation_id == investigation_id,
                ApprovalAction.action_type == action_type,
            )
            .order_by(ApprovalAction.created_at.desc())
        )
        return result.scalars().all()
