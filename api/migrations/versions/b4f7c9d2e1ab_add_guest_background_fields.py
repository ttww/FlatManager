"""add guest background fields

Revision ID: b4f7c9d2e1ab
Revises: a1b2c3d4e5f6
Create Date: 2026-06-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b4f7c9d2e1ab"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "apartments",
        sa.Column("guest_background_filename", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "apartments",
        sa.Column("guest_background_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("apartments", "guest_background_updated_at")
    op.drop_column("apartments", "guest_background_filename")
