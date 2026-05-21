"""
Add investigation_artifacts, notifications tables + GIN indexes on JSONB columns.

Revision: 0003
Depends on: 0002

Changes:
  1. CREATE TABLE investigation_artifacts
  2. CREATE TABLE notifications  (+ notification_status_enum)
  3. GIN indexes on investigations JSONB columns:
       - ai_reasoning
       - evidence_found
       - metadata
  4. GIN index on investigation_artifacts.metadata
  5. GIN index on notifications.metadata
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New ENUM: notification_status_enum ────────────────────────────────
    notification_status_enum = sa.Enum(
        "PENDING", "SENT", "FAILED", "SUPPRESSED",
        name="notification_status_enum",
        _create_events=False,
    )
    notification_status_enum.create(op.get_bind(), checkfirst=True)

    # ── TABLE: investigation_artifacts ─────────────────────────────────────
    op.create_table(
        "investigation_artifacts",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(100), nullable=False),
        sa.Column("artifact_name", sa.String(512), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_artifacts_investigation_id",
        "investigation_artifacts", ["investigation_id"],
    )
    op.create_index(
        "ix_artifacts_artifact_type",
        "investigation_artifacts", ["artifact_type"],
    )
    op.create_index(
        "ix_artifacts_created_at",
        "investigation_artifacts", ["created_at"],
    )
    op.create_index(
        "ix_artifacts_inv_type",
        "investigation_artifacts", ["investigation_id", "artifact_type"],
    )
    # GIN index on artifact metadata for containment queries
    op.execute("""
        CREATE INDEX idx_artifacts_metadata_gin
        ON investigation_artifacts
        USING GIN(metadata);
    """)

    # ── TABLE: notifications ───────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=True),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("recipient", sa.String(512), nullable=False),
        sa.Column(
            "status", notification_status_enum, nullable=False,
            server_default="PENDING",
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_notifications_investigation_id",
        "notifications", ["investigation_id"],
    )
    op.create_index(
        "ix_notifications_notification_type",
        "notifications", ["notification_type"],
    )
    op.create_index(
        "ix_notifications_status",
        "notifications", ["status"],
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications", ["created_at"],
    )
    op.create_index(
        "ix_notifications_inv_status",
        "notifications", ["investigation_id", "status"],
    )
    op.create_index(
        "ix_notifications_type_status",
        "notifications", ["notification_type", "status"],
    )
    # GIN index on notification metadata
    op.execute("""
        CREATE INDEX idx_notifications_metadata_gin
        ON notifications
        USING GIN(metadata);
    """)

    # ── GIN indexes on investigations JSONB columns ────────────────────────
    # These dramatically speed up containment (@>) and existence (?) queries
    # on AI reasoning, evidence, and metadata.
    op.execute("""
        CREATE INDEX idx_investigations_ai_reasoning_gin
        ON investigations
        USING GIN(ai_reasoning);
    """)
    op.execute("""
        CREATE INDEX idx_investigations_evidence_found_gin
        ON investigations
        USING GIN(evidence_found);
    """)
    op.execute("""
        CREATE INDEX idx_investigation_metadata_gin
        ON investigations
        USING GIN(metadata);
    """)


def downgrade() -> None:
    # Drop GIN indexes on investigations
    op.execute("DROP INDEX IF EXISTS idx_investigation_metadata_gin;")
    op.execute("DROP INDEX IF EXISTS idx_investigations_evidence_found_gin;")
    op.execute("DROP INDEX IF EXISTS idx_investigations_ai_reasoning_gin;")

    # Drop notifications
    op.execute("DROP INDEX IF EXISTS idx_notifications_metadata_gin;")
    op.drop_table("notifications")

    # Drop artifacts
    op.execute("DROP INDEX IF EXISTS idx_artifacts_metadata_gin;")
    op.drop_table("investigation_artifacts")

    # Drop enum
    op.execute("DROP TYPE IF EXISTS notification_status_enum;")
