"""
Generic async base DAO / Repository.

All domain DAOs extend `BaseDAO[ModelT]`.  Provides standard CRUD operations
so domain DAOs only need to add specialised query methods.

Usage::

    class ContainerDAO(BaseDAO[Container]):
        model = Container

    # In a FastAPI handler:
    async with get_db_session() as session:
        dao = ContainerDAO(session)
        container = await dao.get_by_id(some_uuid)
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, Sequence, Type, TypeVar

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseDAO(Generic[ModelT]):
    """Generic async repository providing standard CRUD for any ORM model."""

    # Subclasses must set this:
    model: Type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    async def create(self, **kwargs: Any) -> ModelT:
        """Insert a new record and return the refreshed instance."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()          # assign DB-generated defaults
        await self.session.refresh(instance)
        return instance

    async def create_from_dict(self, data: dict[str, Any]) -> ModelT:
        return await self.create(**data)

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------

    async def get_by_id(self, record_id: uuid.UUID) -> ModelT | None:
        """Fetch a single record by primary key (UUID)."""
        result = await self.session.execute(
            select(self.model).where(self.model.id == record_id)  # type: ignore[attr-defined]
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
        order_by: Any = None,
    ) -> Sequence[ModelT]:
        """Paginated fetch of all records."""
        stmt = select(self.model).limit(limit).offset(offset)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        """Total row count for the table."""
        result = await self.session.execute(
            select(func.count()).select_from(self.model)
        )
        return result.scalar_one()

    async def exists(self, record_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(self.model).where(
                self.model.id == record_id  # type: ignore[attr-defined]
            )
        )
        return result.scalar_one() > 0

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    async def update_by_id(
        self,
        record_id: uuid.UUID,
        **kwargs: Any,
    ) -> ModelT | None:
        """
        Bulk-update columns by primary key.

        Strips `None` values so callers can pass optional fields freely.
        Returns the refreshed instance or `None` if not found.
        """
        payload = {k: v for k, v in kwargs.items() if v is not None}
        if not payload:
            return await self.get_by_id(record_id)

        await self.session.execute(
            update(self.model)
            .where(self.model.id == record_id)  # type: ignore[attr-defined]
            .values(**payload)
            .execution_options(synchronize_session="fetch")
        )
        await self.session.flush()
        return await self.get_by_id(record_id)

    async def update_instance(self, instance: ModelT, **kwargs: Any) -> ModelT:
        """Update an already-loaded ORM instance in-place."""
        for key, value in kwargs.items():
            if value is not None:
                setattr(instance, key, value)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    async def delete_by_id(self, record_id: uuid.UUID) -> bool:
        """Delete a record.  Returns True if something was deleted."""
        result = await self.session.execute(
            delete(self.model).where(
                self.model.id == record_id  # type: ignore[attr-defined]
            )
        )
        return result.rowcount > 0  # type: ignore[return-value]
