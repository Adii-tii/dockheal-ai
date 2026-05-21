"""
Add 5 new fields to investigations table.

Revision: 0002
Depends on: 0001

Changes:
  - ADD COLUMN current_step         VARCHAR(255)
  - ADD COLUMN recovery_status      recovery_status_enum  NOT NULL DEFAULT 'UNKNOWN'
  - ADD COLUMN approval_timeout_at  TIMESTAMPTZ
  - ADD COLUMN is_auto_recovery     BOOLEAN NOT NULL DEFAULT FALSE
  - ADD COLUMN incident_hash        VARCHAR(64)
  - CREATE TYPE recovery_status_enum
  - CREATE INDEX ix_investigations_incident_hash
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create the new enum type ───────────────────────────────────────────
    recovery_status_enum = sa.Enum(
        "TEMPORARY", "PERMANENT", "PARTIAL", "UNKNOWN",
        name="recovery_status_enum",
        _create_events=False,
    )
    recovery_status_enum.create(op.get_bind(), checkfirst=True)

    # ── Add columns (safe with existing data — all nullable or have defaults) ─
    op.add_column(
        "investigations",
        sa.Column(
            "current_step",
            sa.String(255),
            nullable=True,
            comment="Live label of the AI's current action step",
        ),
    )
    op.add_column(
        "investigations",
        sa.Column(
            "recovery_status",
            recovery_status_enum,
            nullable=False,
            server_default="UNKNOWN",
            comment="Permanence of the applied fix",
        ),
    )
    op.add_column(
        "investigations",
        sa.Column(
            "approval_timeout_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Hard deadline for human approval; auto-rejects when exceeded",
        ),
    )
    op.add_column(
        "investigations",
        sa.Column(
            "is_auto_recovery",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
            comment="True when remediation was applied automatically",
        ),
    )
    op.add_column(
        "investigations",
        sa.Column(
            "incident_hash",
            sa.String(64),
            nullable=True,
            comment="SHA-256 fingerprint for deduplication",
        ),
    )

    # ── Index for fast deduplication lookups ──────────────────────────────
    op.create_index(
        "ix_investigations_incident_hash",
        "investigations",
        ["incident_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_investigations_incident_hash", table_name="investigations")
    op.drop_column("investigations", "incident_hash")
    op.drop_column("investigations", "is_auto_recovery")
    op.drop_column("investigations", "approval_timeout_at")
    op.drop_column("investigations", "recovery_status")
    op.drop_column("investigations", "current_step")
    op.execute("DROP TYPE IF EXISTS recovery_status_enum;")
