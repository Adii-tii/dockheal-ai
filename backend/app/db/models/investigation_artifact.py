"""
ORM model — investigation_artifacts table.

First-class storage for every artifact produced during an investigation.
Rather than embedding raw blobs inside JSONB columns on the investigations row,
each artifact gets its own row with a typed `artifact_type`, a human-readable
name, and a `storage_path` pointing to wherever the artifact lives
(local disk, S3, GCS, or a future artifact store).

Artifact types (not enforced as a PG enum so new types never need migrations):
    log_snapshot       — captured log extract
    stack_trace        — captured exception/traceback
    screenshot         — UI or dashboard capture
    sandbox_output     — stdout/stderr from a sandbox run
    ai_reasoning_dump  — full AI chain-of-thought export
    metric_export      — time-series metric snapshot (CSV/JSON)
    config_diff        — config file before/after comparison
    custom             — anything else
"""

import uuid
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import func

from app.db.models.base import Base, UUIDMixin


class InvestigationArtifact(Base, UUIDMixin):
    """A single artifact produced or captured during an investigation."""

    __tablename__ = "investigation_artifacts"

    # ── Foreign key ────────────────────────────────────────────────────────
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Classification ─────────────────────────────────────────────────────
    artifact_type: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment=(
            "Free-form type tag: log_snapshot | stack_trace | screenshot | "
            "sandbox_output | ai_reasoning_dump | metric_export | config_diff | custom"
        ),
    )
    artifact_name: Mapped[str] = mapped_column(
        String(512), nullable=False,
        comment="Human-readable filename or label, e.g. 'nginx_error.log'"
    )

    # ── Storage reference ──────────────────────────────────────────────────
    storage_path: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment=(
            "Where the artifact lives: local path, s3://bucket/key, "
            "gs://bucket/key, or an HTTP URL to an artifact store"
        ),
    )

    # ── Immutable timestamp ────────────────────────────────────────────────
    created_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── JSONB — flexible metadata ──────────────────────────────────────────
    metadata_: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata",
        JSONB, nullable=True, default=dict,
        comment=(
            "Arbitrary key/value pairs: file_size, mime_type, sha256_checksum, "
            "tool_name, step_index, etc.  GIN-indexed for query flexibility."
        ),
    )

    # ── Relationships ──────────────────────────────────────────────────────
    investigation: Mapped["Investigation"] = relationship(  # noqa: F821
        "Investigation", back_populates="artifacts"
    )

    # ── Indexes ────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_artifacts_inv_type", "investigation_id", "artifact_type"),
        Index("ix_artifacts_created_at", "created_at"),
        # GIN index on metadata for fast JSONB containment queries
        # e.g.  WHERE metadata @> '{"mime_type": "text/plain"}'
        Index(
            "idx_artifacts_metadata_gin",
            "metadata",
            postgresql_using="gin",
        ),
        Index(
            "ix_artifacts_inv_created",
            "investigation_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<InvestigationArtifact id={self.id} type={self.artifact_type!r} "
            f"name={self.artifact_name!r}>"
        )
