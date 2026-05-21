"""
Initial schema migration — DockHeal v1.0

Revision: 0001
Creates all 8 core tables with:
  - PostgreSQL native ENUM types
  - UUID primary keys
  - JSONB columns for AI / system data
  - Proper foreign keys with CASCADE deletes
  - All required indexes
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, create_type=False, _create_events=False)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ── ENUM TYPES ─────────────────────────────────────────────────────────
    container_status_enum = _create_enum(
        "container_status_enum",
        "running", "stopped", "exited", "paused",
        "restarting", "dead", "created", "unknown",
    )
    health_status_enum = _create_enum(
        "health_status_enum",
        "healthy", "unhealthy", "starting", "none",
    )
    severity_level_enum = _create_enum(
        "severity_level_enum", "P0", "P1", "P2", "P3",
    )
    lifecycle_state_enum = _create_enum(
        "lifecycle_state_enum",
        "INITIATED", "ANALYZING", "AWAITING_APPROVAL",
        "REMEDIATING", "RESOLVED", "REJECTED", "ESCALATED", "BLOCKED",
    )
    source_type_enum = _create_enum(
        "source_type_enum", "AI_AGENT", "HUMAN", "SYSTEM",
    )
    action_type_enum = _create_enum(
        "action_type_enum", "APPROVE", "REJECT",
    )
    execution_status_enum = _create_enum(
        "execution_status_enum",
        "PENDING", "RUNNING", "SUCCESS", "FAILED", "ROLLED_BACK",
    )
    sandbox_status_enum = _create_enum(
        "sandbox_status_enum",
        "PENDING", "RUNNING", "COMPLETED", "FAILED", "CLEANED",
    )

    # Create all enum types in DB
    for enum in [
        container_status_enum, health_status_enum, severity_level_enum,
        lifecycle_state_enum, source_type_enum, action_type_enum,
        execution_status_enum, sandbox_status_enum,
    ]:
        enum.create(op.get_bind(), checkfirst=True)

    # ── TABLE: containers ──────────────────────────────────────────────────
    op.create_table(
        "containers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("container_name", sa.String(255), nullable=False, unique=True),
        sa.Column("image_name", sa.String(512), nullable=True),
        sa.Column("status", container_status_enum, nullable=False,
                  server_default="unknown"),
        sa.Column("health_status", health_status_enum, nullable=False,
                  server_default="none"),
        sa.Column("auto_restart", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("environment", sa.String(100), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels", JSONB, nullable=True),
        sa.Column("ports", JSONB, nullable=True),
        sa.Column("runtime_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_containers_container_name", "containers",
                    ["container_name"], unique=True)
    op.create_index("ix_containers_status_last_seen", "containers",
                    ["status", "last_seen"])

    # ── TABLE: investigations ──────────────────────────────────────────────
    op.create_table(
        "investigations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("container_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("incident_summary", sa.Text, nullable=True),
        sa.Column("severity_level", severity_level_enum, nullable=False,
                  server_default="P2"),
        sa.Column("lifecycle_state", lifecycle_state_enum, nullable=False,
                  server_default="INITIATED"),
        sa.Column("ai_confidence_score", sa.Float, nullable=True),
        sa.Column("status", sa.String(100), nullable=True),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("proposed_action", sa.Text, nullable=True),
        sa.Column("auto_restart_allowed", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("approval_required", sa.Boolean, nullable=False,
                  server_default=sa.text("true")),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ai_reasoning", JSONB, nullable=True),
        sa.Column("evidence_found", JSONB, nullable=True),
        sa.Column("contributing_factors", JSONB, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["container_id"], ["containers.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_investigations_container_id", "investigations",
                    ["container_id"])
    op.create_index("ix_investigations_lifecycle_state", "investigations",
                    ["lifecycle_state"])
    op.create_index("ix_investigations_severity_level", "investigations",
                    ["severity_level"])
    op.create_index("ix_investigations_created_at", "investigations",
                    ["created_at"])
    op.create_index("ix_investigations_state_severity", "investigations",
                    ["lifecycle_state", "severity_level"])
    op.create_index("ix_investigations_container_state", "investigations",
                    ["container_id", "lifecycle_state"])

    # Auto-update `updated_at` via trigger
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
    """)
    for tbl in ("containers", "investigations"):
        op.execute(f"""
            CREATE TRIGGER {tbl}_updated_at
            BEFORE UPDATE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
        """)

    # ── TABLE: investigation_timeline_events ───────────────────────────────
    op.create_table(
        "investigation_timeline_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_type", source_type_enum, nullable=False,
                  server_default="AI_AGENT"),
        sa.Column("severity", severity_level_enum, nullable=True),
        sa.Column("raw_data", JSONB, nullable=True),
        sa.Column("tool_output", JSONB, nullable=True),
        sa.Column("extra_context", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_timeline_investigation_id",
                    "investigation_timeline_events", ["investigation_id"])
    op.create_index("ix_timeline_event_type",
                    "investigation_timeline_events", ["event_type"])
    op.create_index("ix_timeline_created_at",
                    "investigation_timeline_events", ["created_at"])
    op.create_index("ix_timeline_inv_created",
                    "investigation_timeline_events",
                    ["investigation_id", "created_at"])
    op.create_index("ix_timeline_inv_event_type",
                    "investigation_timeline_events",
                    ["investigation_id", "event_type"])

    # ── TABLE: rca_reports ─────────────────────────────────────────────────
    op.create_table(
        "rca_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("rca_version", sa.Integer, nullable=False,
                  server_default="1"),
        sa.Column("incident_summary", sa.Text, nullable=True),
        sa.Column("impact_assessment", sa.Text, nullable=True),
        sa.Column("what_failed", sa.Text, nullable=True),
        sa.Column("why_it_happened", sa.Text, nullable=True),
        sa.Column("action_proposed", sa.Text, nullable=True),
        sa.Column("recovery_status", sa.String(100), nullable=True),
        sa.Column("long_term_prevention", sa.Text, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("ai_reasoning_summary", sa.Text, nullable=True),
        sa.Column("evidence_found", JSONB, nullable=True),
        sa.Column("contributing_factors", JSONB, nullable=True),
        sa.Column("recommendations", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_rca_investigation_id", "rca_reports",
                    ["investigation_id"])
    op.create_index("ix_rca_created_at", "rca_reports", ["created_at"])
    op.create_index("ix_rca_inv_version", "rca_reports",
                    ["investigation_id", "rca_version"])

    # ── TABLE: approval_actions ────────────────────────────────────────────
    op.create_table(
        "approval_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", action_type_enum, nullable=False),
        sa.Column("approved_by", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("source", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_approval_investigation_id", "approval_actions",
                    ["investigation_id"])
    op.create_index("ix_approval_inv_created", "approval_actions",
                    ["investigation_id", "created_at"])

    # ── TABLE: sandbox_environments ────────────────────────────────────────
    op.create_table(
        "sandbox_environments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("environment_name", sa.String(255), nullable=False),
        sa.Column("status", sandbox_status_enum, nullable=False,
                  server_default="PENDING"),
        sa.Column("purpose", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cloned_resources", JSONB, nullable=True),
        sa.Column("findings", JSONB, nullable=True),
        sa.Column("actions_tested", JSONB, nullable=True),
        sa.Column("validation_results", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_sandbox_investigation_id", "sandbox_environments",
                    ["investigation_id"])
    op.create_index("ix_sandbox_status", "sandbox_environments", ["status"])
    op.create_index("ix_sandbox_inv_status", "sandbox_environments",
                    ["investigation_id", "status"])

    # ── TABLE: recovery_actions ────────────────────────────────────────────
    op.create_table(
        "recovery_actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action_name", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("execution_status", execution_status_enum, nullable=False,
                  server_default="PENDING"),
        sa.Column("execution_logs", sa.Text, nullable=True),
        sa.Column("rollback_available", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parameters", JSONB, nullable=True),
        sa.Column("validation_results", JSONB, nullable=True),
        sa.Column("rollback_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["investigation_id"], ["investigations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_recovery_investigation_id", "recovery_actions",
                    ["investigation_id"])
    op.create_index("ix_recovery_execution_status", "recovery_actions",
                    ["execution_status"])
    op.create_index("ix_recovery_inv_status", "recovery_actions",
                    ["investigation_id", "execution_status"])
    op.create_index("ix_recovery_created_at", "recovery_actions",
                    ["created_at"])

    # ── TABLE: system_metrics ──────────────────────────────────────────────
    op.create_table(
        "system_metrics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("container_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cpu_usage", sa.Float, nullable=True),
        sa.Column("memory_usage", sa.Float, nullable=True),
        sa.Column("disk_usage", sa.Float, nullable=True),
        sa.Column("network_usage", sa.Float, nullable=True),
        sa.Column("anomaly_score", sa.Float, nullable=True),
        sa.Column("raw_metrics", JSONB, nullable=True),
        sa.Column("anomaly_metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["container_id"], ["containers.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_metrics_container_id", "system_metrics",
                    ["container_id"])
    op.create_index("ix_metrics_created_at", "system_metrics", ["created_at"])
    op.create_index("ix_metrics_container_created", "system_metrics",
                    ["container_id", "created_at"])
    op.create_index("ix_metrics_anomaly_score", "system_metrics",
                    ["anomaly_score"])


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("system_metrics")
    op.drop_table("recovery_actions")
    op.drop_table("sandbox_environments")
    op.drop_table("approval_actions")
    op.drop_table("rca_reports")
    op.drop_table("investigation_timeline_events")
    op.drop_table("investigations")
    op.drop_table("containers")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column CASCADE;")

    # Drop enum types
    for enum_name in [
        "sandbox_status_enum",
        "execution_status_enum",
        "action_type_enum",
        "source_type_enum",
        "lifecycle_state_enum",
        "severity_level_enum",
        "health_status_enum",
        "container_status_enum",
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
