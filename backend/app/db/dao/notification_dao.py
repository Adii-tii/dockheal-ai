"""
DAO — Notification repository.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.notification import Notification
from app.db.models.enums import NotificationStatus


class NotificationDAO(BaseDAO[Notification]):
    model = Notification

    async def get_for_investigation(
        self,
        investigation_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[Notification]:
        """All notifications linked to a specific investigation."""
        result = await self.session.execute(
            select(Notification)
            .where(Notification.investigation_id == investigation_id)
            .order_by(Notification.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_by_status(
        self,
        status: NotificationStatus,
        *,
        limit: int = 100,
    ) -> Sequence[Notification]:
        """Return notifications filtered by delivery status (e.g. PENDING for retry)."""
        result = await self.session.execute(
            select(Notification)
            .where(Notification.status == status)
            .order_by(Notification.created_at.asc())
            .limit(limit)
        )
        return result.scalars().all()

    async def get_pending(self, *, limit: int = 50) -> Sequence[Notification]:
        """Convenience: return PENDING notifications oldest-first for the delivery worker."""
        return await self.get_by_status(NotificationStatus.PENDING, limit=limit)

    async def get_failed(self, *, limit: int = 50) -> Sequence[Notification]:
        """Return FAILED notifications for retry processing."""
        return await self.get_by_status(NotificationStatus.FAILED, limit=limit)

    async def get_by_type(
        self,
        notification_type: str,
        *,
        limit: int = 100,
    ) -> Sequence[Notification]:
        """Return notifications for a specific channel type (e.g. 'SLACK')."""
        result = await self.session.execute(
            select(Notification)
            .where(Notification.notification_type == notification_type)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def mark_sent(
        self,
        notification_id: uuid.UUID,
        **metadata_updates: object,
    ) -> Notification | None:
        """
        Transition a notification to SENT and optionally merge delivery metadata
        (e.g. message_id, thread_ts) in a single update call.
        """
        from datetime import datetime, timezone
        return await self.update_by_id(
            notification_id,
            status=NotificationStatus.SENT,
            sent_at=datetime.now(timezone.utc),
            **metadata_updates,
        )

    async def mark_failed(
        self,
        notification_id: uuid.UUID,
        error_message: str | None = None,
    ) -> Notification | None:
        """Transition a notification to FAILED and record the error reason."""
        existing = await self.get_by_id(notification_id)
        if existing is None:
            return None
        meta = dict(existing.metadata_ or {})
        if error_message:
            meta["last_error"] = error_message
            meta["retry_count"] = meta.get("retry_count", 0) + 1
        return await self.update_by_id(
            notification_id,
            status=NotificationStatus.FAILED,
            metadata_=meta,
        )
