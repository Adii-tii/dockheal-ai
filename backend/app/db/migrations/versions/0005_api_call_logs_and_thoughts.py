"""0005 — add api_call_logs table and thoughts column to investigations

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add `thoughts` column to investigations
    op.add_column(
        "investigations",
        sa.Column(
            "thoughts",
            sa.Text(),
            nullable=True,
            comment="Full raw AI reasoning stream (think-aloud text from the LLM)",
        ),
    )

    # 2. Create api_call_logs table
    op.create_table(
        "api_call_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_api_call_logs_created_at",
        "api_call_logs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_call_logs_created_at", table_name="api_call_logs")
    op.drop_table("api_call_logs")
    op.drop_column("investigations", "thoughts")
