"""0006 — add is_manually_stopped column to containers

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-22

Persists whether a container was deliberately stopped by the user (via
docker stop / docker kill).  This flag is seeded into the in-memory
`manually_stopped` set on backend startup, preventing the monitor loop
from treating user-stopped containers as unexpected incidents after a
server restart.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "containers",
        sa.Column(
            "is_manually_stopped",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True when a user explicitly stopped this container via docker stop/kill",
        ),
    )


def downgrade() -> None:
    op.drop_column("containers", "is_manually_stopped")
