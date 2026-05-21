"""
Shared pagination helper.

Usage::

    from app.db.utils.pagination import PaginationParams, paginate

    @router.get("/investigations")
    async def list_investigations(
        pagination: PaginationParams = Depends(),
        session: AsyncSession = Depends(get_db_session),
    ):
        dao = InvestigationDAO(session)
        return await paginate(dao, pagination)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Sequence, TypeVar

from fastapi import Query
from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# FastAPI dependency — extract page / page_size from query string
# ---------------------------------------------------------------------------

class PaginationParams:
    """
    FastAPI-compatible pagination query parameters.

    Defaults: page=1, page_size=20, max page_size=200.
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="1-indexed page number"),
        page_size: int = Query(20, ge=1, le=200, description="Items per page"),
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


# ---------------------------------------------------------------------------
# Paginated response envelope
# ---------------------------------------------------------------------------

class PagedResponse(BaseModel, Generic[T]):
    """Generic paginated API response."""

    items: list[Any]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(
        cls,
        items: Sequence[Any],
        total: int,
        pagination: PaginationParams,
    ) -> "PagedResponse":
        pages = max(1, -(-total // pagination.page_size))  # ceil division
        return cls(
            items=list(items),
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            pages=pages,
        )


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------

async def paginate(dao: Any, pagination: PaginationParams) -> PagedResponse:
    """
    Fetch a page of results from any DAO that implements `get_all` and `count`.
    """
    total = await dao.count()
    items = await dao.get_all(
        limit=pagination.limit,
        offset=pagination.offset,
    )
    return PagedResponse.build(items, total, pagination)
