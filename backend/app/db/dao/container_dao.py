"""
DAO — Container repository.

Extends BaseDAO with container-specific query methods.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select

from app.db.dao.base_dao import BaseDAO
from app.db.models.container import Container
from app.db.models.enums import ContainerStatus, HealthStatus


class ContainerDAO(BaseDAO[Container]):
    model = Container

    # ------------------------------------------------------------------
    # Domain-specific queries
    # ------------------------------------------------------------------

    async def get_by_name(self, container_name: str) -> Container | None:
        """Look up a container by its unique Docker name."""
        result = await self.session.execute(
            select(Container).where(Container.container_name == container_name)
        )
        return result.scalar_one_or_none()

    async def get_by_runtime_id(self, runtime_id: str) -> Container | None:
        """Look up a container by its unique Docker runtime ID."""
        result = await self.session.execute(
            select(Container).where(Container.runtime_id == runtime_id)
        )
        return result.scalar_one_or_none()

    async def get_by_status(
        self, status: ContainerStatus, *, limit: int = 100, offset: int = 0
    ) -> Sequence[Container]:
        result = await self.session.execute(
            select(Container)
            .where(Container.status == status)
            .order_by(Container.last_seen.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_unhealthy(self) -> Sequence[Container]:
        """Return all containers that are not healthy."""
        result = await self.session.execute(
            select(Container).where(
                Container.health_status == HealthStatus.UNHEALTHY
            )
        )
        return result.scalars().all()

    async def get_auto_restart_enabled(self) -> Sequence[Container]:
        result = await self.session.execute(
            select(Container).where(Container.auto_restart.is_(True))
        )
        return result.scalars().all()

    async def touch_last_seen(self, container_name: str) -> Container | None:
        """Update `last_seen` timestamp to now for a named container."""
        container = await self.get_by_name(container_name)
        if container is None:
            return None
        return await self.update_instance(
            container, last_seen=datetime.now(timezone.utc)
        )

    async def upsert_by_name(self, **kwargs: object) -> Container:
        """
        Insert or update a container by its name.

        If a container with the given `container_name` already exists,
        update its fields; otherwise create a new record.
        """
        name = str(kwargs["container_name"])
        existing = await self.get_by_name(name)
        if existing:
            return await self.update_instance(existing, **kwargs)
        return await self.create(**kwargs)

    async def upsert_by_runtime_id(self, runtime_id: str, **kwargs: object) -> Container:
        """
        Insert or update a container by its runtime ID.

        If a container with the given `runtime_id` already exists,
        update its fields; otherwise create a new record.
        """
        existing = await self.get_by_runtime_id(runtime_id)
        if existing:
            return await self.update_instance(existing, **kwargs)
        return await self.create(runtime_id=runtime_id, **kwargs)
