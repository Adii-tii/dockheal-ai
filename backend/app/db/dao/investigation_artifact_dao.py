"""
DAO — InvestigationArtifact repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.investigation_artifact import InvestigationArtifact


class InvestigationArtifactDAO(BaseDAO[InvestigationArtifact]):
    model = InvestigationArtifact

    async def get_for_investigation(
        self,
        investigation_id: uuid.UUID,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> Sequence[InvestigationArtifact]:
        """Return all artifacts for an investigation, oldest first."""
        result = await self.session.execute(
            select(InvestigationArtifact)
            .where(InvestigationArtifact.investigation_id == investigation_id)
            .order_by(InvestigationArtifact.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_type(
        self,
        investigation_id: uuid.UUID,
        artifact_type: str,
    ) -> Sequence[InvestigationArtifact]:
        """Return artifacts filtered by type, e.g. 'log_snapshot'."""
        result = await self.session.execute(
            select(InvestigationArtifact)
            .where(
                InvestigationArtifact.investigation_id == investigation_id,
                InvestigationArtifact.artifact_type == artifact_type,
            )
            .order_by(InvestigationArtifact.created_at.asc())
        )
        return result.scalars().all()

    async def get_without_storage_path(
        self, investigation_id: uuid.UUID
    ) -> Sequence[InvestigationArtifact]:
        """
        Return artifacts whose storage_path is still NULL.
        Useful for a background upload job that backfills remote paths.
        """
        result = await self.session.execute(
            select(InvestigationArtifact)
            .where(
                InvestigationArtifact.investigation_id == investigation_id,
                InvestigationArtifact.storage_path.is_(None),
            )
        )
        return result.scalars().all()
