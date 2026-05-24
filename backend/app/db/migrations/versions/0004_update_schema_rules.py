"""
Update schema rules.

Revision: 0004
Depends on: 0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Update lifecycle_state_enum ─────────────────────────────────────
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state DROP DEFAULT")
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state TYPE VARCHAR(100)")
    op.execute("DROP TYPE IF EXISTS lifecycle_state_enum")

    lifecycle_state_enum = sa.Enum(
        "DETECTED", "INVESTIGATING", "RCA_IDENTIFIED", "AWAITING_APPROVAL",
        "RECOVERING", "VALIDATING", "MONITORING", "RESOLVED", "REJECTED", "TIMED_OUT", "ESCALATED",
        name="lifecycle_state_enum",
        _create_events=False
    )
    lifecycle_state_enum.create(op.get_bind(), checkfirst=True)

    # Remap old values
    op.execute("UPDATE investigations SET lifecycle_state = 'DETECTED' WHERE lifecycle_state = 'INITIATED'")
    op.execute("UPDATE investigations SET lifecycle_state = 'INVESTIGATING' WHERE lifecycle_state = 'ANALYZING'")
    op.execute("UPDATE investigations SET lifecycle_state = 'RECOVERING' WHERE lifecycle_state = 'REMEDIATING'")
    op.execute("UPDATE investigations SET lifecycle_state = 'ESCALATED' WHERE lifecycle_state = 'BLOCKED'")
    op.execute(
        "UPDATE investigations SET lifecycle_state = 'DETECTED' "
        "WHERE lifecycle_state NOT IN ("
        "'DETECTED', 'INVESTIGATING', 'RCA_IDENTIFIED', 'AWAITING_APPROVAL', "
        "'RECOVERING', 'VALIDATING', 'MONITORING', 'RESOLVED', 'REJECTED', 'TIMED_OUT', 'ESCALATED'"
        ")"
    )

    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state TYPE lifecycle_state_enum USING lifecycle_state::lifecycle_state_enum")
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state SET DEFAULT 'DETECTED'::lifecycle_state_enum")

    # ── 2. Modify investigations columns ───────────────────────────────────
    op.drop_column("investigations", "ai_confidence_score")
    op.execute("DROP INDEX IF EXISTS idx_investigations_ai_reasoning_gin")
    op.drop_column("investigations", "ai_reasoning")

    op.add_column("investigations", sa.Column("ai_reasoning_summary", sa.Text(), nullable=True))
    op.add_column("investigations", sa.Column("decision_trace", JSONB(), nullable=True, server_default="{}"))
    op.add_column("investigations", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("investigations", sa.Column("detected_signals", JSONB(), nullable=True, server_default="[]"))
    op.add_column("investigations", sa.Column("correlation_id", sa.String(255), nullable=True))
    op.add_column("investigations", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("investigations", sa.Column("created_by", sa.String(100), nullable=False, server_default="monitor_worker"))

    op.create_index("ix_investigations_correlation_id", "investigations", ["correlation_id"])
    op.execute("CREATE INDEX idx_investigations_decision_trace_gin ON investigations USING GIN(decision_trace)")
    op.execute("CREATE INDEX idx_investigations_detected_signals_gin ON investigations USING GIN(detected_signals)")

    # ── 3. Partial unique index for active investigations per container ────
    op.execute(
        "CREATE UNIQUE INDEX idx_unique_active_investigation_per_container "
        "ON investigations (container_id) "
        "WHERE lifecycle_state NOT IN ('RESOLVED', 'REJECTED', 'TIMED_OUT', 'ESCALATED')"
    )

    # ── 4. Containers table updates ────────────────────────────────────────
    op.add_column("containers", sa.Column("runtime_id", sa.String(255), nullable=True))
    op.execute("UPDATE containers SET runtime_id = container_name WHERE runtime_id IS NULL")
    op.alter_column("containers", "runtime_id", nullable=False)
    op.drop_constraint("containers_container_name_key", "containers", type_="unique")
    op.drop_index("ix_containers_container_name", table_name="containers")
    op.create_index("ix_containers_container_name", "containers", ["container_name"])
    op.create_unique_constraint("uq_containers_runtime_id", "containers", ["runtime_id"])
    op.create_index("ix_containers_runtime_id", "containers", ["runtime_id"])

    # ── 5. Timeline events updates ─────────────────────────────────────────
    op.add_column("investigation_timeline_events", sa.Column("sequence_number", sa.Integer(), nullable=True))
    op.add_column("investigation_timeline_events", sa.Column("correlation_id", sa.String(255), nullable=True))
    op.create_index("ix_timeline_correlation_id", "investigation_timeline_events", ["correlation_id"])

    op.execute("""
        WITH seqs AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY investigation_id ORDER BY created_at) as seq
            FROM investigation_timeline_events
        )
        UPDATE investigation_timeline_events
        SET sequence_number = seqs.seq
        FROM seqs
        WHERE investigation_timeline_events.id = seqs.id
    """)
    op.alter_column("investigation_timeline_events", "sequence_number", nullable=False)
    op.create_unique_constraint("uq_timeline_inv_sequence", "investigation_timeline_events", ["investigation_id", "sequence_number"])

    # ── 6. RCAReport updates ───────────────────────────────────────────────
    op.add_column("rca_reports", sa.Column("is_final", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    # ── 7. RecoveryAction updates ──────────────────────────────────────────
    op.add_column("recovery_actions", sa.Column("rollback_executed", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("recovery_actions", sa.Column("rollback_status", sa.String(100), nullable=True))
    op.add_column("recovery_actions", sa.Column("correlation_id", sa.String(255), nullable=True))
    op.create_index("ix_recovery_correlation_id", "recovery_actions", ["correlation_id"])
    op.create_index("ix_recovery_inv_created", "recovery_actions", ["investigation_id", "created_at"])

    # ── 8. Notification updates ────────────────────────────────────────────
    op.add_column("notifications", sa.Column("correlation_id", sa.String(255), nullable=True))
    op.create_index("ix_notifications_correlation_id", "notifications", ["correlation_id"])
    op.create_index("ix_notifications_inv_created", "notifications", ["investigation_id", "created_at"])

    # ── 9. InvestigationArtifact updates ───────────────────────────────────
    op.create_index("ix_artifacts_inv_created", "investigation_artifacts", ["investigation_id", "created_at"])

    # ── 10. Create system_metrics_hourly table ─────────────────────────────
    op.create_table(
        "system_metrics_hourly",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("container_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cpu_usage_avg", sa.Float(), nullable=True),
        sa.Column("memory_usage_avg", sa.Float(), nullable=True),
        sa.Column("disk_usage_avg", sa.Float(), nullable=True),
        sa.Column("network_usage_avg", sa.Float(), nullable=True),
        sa.Column("anomaly_score_max", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["container_id"], ["containers.id"], ondelete="CASCADE")
    )
    op.create_index("ix_metrics_hourly_container_created", "system_metrics_hourly", ["container_id", "created_at"])
    op.create_index("ix_metrics_hourly_created_at", "system_metrics_hourly", ["created_at"])


def downgrade() -> None:
    # 10. Drop system_metrics_hourly
    op.drop_table("system_metrics_hourly")

    # 9. Drop artifact index
    op.drop_index("ix_artifacts_inv_created", table_name="investigation_artifacts")

    # 8. Drop notification columns/indexes
    op.drop_index("ix_notifications_inv_created", table_name="notifications")
    op.drop_index("ix_notifications_correlation_id", table_name="notifications")
    op.drop_column("notifications", "correlation_id")

    # 7. Drop recovery_actions columns/indexes
    op.drop_index("ix_recovery_inv_created", table_name="recovery_actions")
    op.drop_index("ix_recovery_correlation_id", table_name="recovery_actions")
    op.drop_column("recovery_actions", "correlation_id")
    op.drop_column("recovery_actions", "rollback_status")
    op.drop_column("recovery_actions", "rollback_executed")

    # 6. Drop rca_reports columns
    op.drop_column("rca_reports", "is_final")

    # 5. Drop timeline event columns/indexes
    op.drop_constraint("uq_timeline_inv_sequence", "investigation_timeline_events", type_="unique")
    op.drop_index("ix_timeline_correlation_id", table_name="investigation_timeline_events")
    op.drop_column("investigation_timeline_events", "correlation_id")
    op.drop_column("investigation_timeline_events", "sequence_number")

    # 4. Containers table downgrade
    op.drop_constraint("uq_containers_runtime_id", "containers", type_="unique")
    op.drop_index("ix_containers_runtime_id", table_name="containers")
    op.drop_index("ix_containers_container_name", table_name="containers")
    op.create_index("ix_containers_container_name", "containers", ["container_name"], unique=True)
    op.create_unique_constraint("containers_container_name_key", "containers", ["container_name"])
    op.drop_column("containers", "runtime_id")

    # 3. Drop active investigation unique index
    op.execute("DROP INDEX IF EXISTS idx_unique_active_investigation_per_container")

    # 2. Drop investigations columns
    op.drop_index("ix_investigations_correlation_id", table_name="investigations")
    op.execute("DROP INDEX IF EXISTS idx_investigations_decision_trace_gin")
    op.execute("DROP INDEX IF EXISTS idx_investigations_detected_signals_gin")
    op.drop_column("investigations", "created_by")
    op.drop_column("investigations", "version")
    op.drop_column("investigations", "correlation_id")
    op.drop_column("investigations", "detected_signals")
    op.drop_column("investigations", "confidence")
    op.drop_column("investigations", "decision_trace")
    op.drop_column("investigations", "ai_reasoning_summary")

    # Restore ai_reasoning and ai_confidence_score
    op.add_column("investigations", sa.Column("ai_confidence_score", sa.Float(), nullable=True))
    op.add_column("investigations", sa.Column("ai_reasoning", JSONB(), nullable=True))
    op.execute("CREATE INDEX idx_investigations_ai_reasoning_gin ON investigations USING GIN(ai_reasoning)")

    # 1. Restore old lifecycle_state_enum
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state DROP DEFAULT")
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state TYPE VARCHAR(100)")
    op.execute("DROP TYPE IF EXISTS lifecycle_state_enum")

    lifecycle_state_enum = sa.Enum(
        "INITIATED", "ANALYZING", "AWAITING_APPROVAL", "REMEDIATING",
        "RESOLVED", "REJECTED", "ESCALATED", "BLOCKED",
        name="lifecycle_state_enum",
        _create_events=False
    )
    lifecycle_state_enum.create(op.get_bind(), checkfirst=True)

    # Re-map values back
    op.execute("UPDATE investigations SET lifecycle_state = 'INITIATED' WHERE lifecycle_state = 'DETECTED'")
    op.execute("UPDATE investigations SET lifecycle_state = 'ANALYZING' WHERE lifecycle_state = 'INVESTIGATING'")
    op.execute("UPDATE investigations SET lifecycle_state = 'REMEDIATING' WHERE lifecycle_state = 'RECOVERING'")
    op.execute("UPDATE investigations SET lifecycle_state = 'BLOCKED' WHERE lifecycle_state IN ('VALIDATING', 'MONITORING', 'ESCALATED')")
    op.execute("UPDATE investigations SET lifecycle_state = 'REJECTED' WHERE lifecycle_state = 'TIMED_OUT'")
    op.execute(
        "UPDATE investigations SET lifecycle_state = 'INITIATED' "
        "WHERE lifecycle_state NOT IN ("
        "'INITIATED', 'ANALYZING', 'AWAITING_APPROVAL', 'REMEDIATING', 'RESOLVED', 'REJECTED', 'ESCALATED', 'BLOCKED'"
        ")"
    )

    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state TYPE lifecycle_state_enum USING lifecycle_state::lifecycle_state_enum")
    op.execute("ALTER TABLE investigations ALTER COLUMN lifecycle_state SET DEFAULT 'INITIATED'::lifecycle_state_enum")
