"""
ORM model — api_call_logs table.

Lightweight audit log for every HTTP request that hits the DockHeal API.
Used by the developer "Call Logs" dashboard to monitor API call volume and
help prevent hitting external AI provider rate limits.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models.base import Base


class ApiCallLog(Base):
    """One row per inbound HTTP request to the DockHeal backend."""

    __tablename__ = "api_call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ApiCallLog {self.method} {self.path} "
            f"→ {self.status_code} at {self.created_at}>"
        )
