"""
FastAPI dependency — async DB session.

Usage in a route handler::

    from app.db.utils.db_session import get_db_session
    from app.db.dao import InvestigationDAO

    @router.get("/investigations/{id}")
    async def get_investigation(
        id: uuid.UUID,
        session: AsyncSession = Depends(get_db_session),
    ):
        dao = InvestigationDAO(session)
        return await dao.get_by_id(id)

The dependency uses an async context manager so the session is always
committed on success and rolled back on exception.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.config.config import AsyncSessionLocal


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield one async database session per request.

    * Commits automatically on clean exit.
    * Rolls back on any unhandled exception.
    * Closes the session regardless of outcome.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
