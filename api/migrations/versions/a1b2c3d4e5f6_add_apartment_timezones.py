"""add apartment timezones

Revision ID: a1b2c3d4e5f6
Revises: 3d3abba05bc0
Create Date: 2026-06-24 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "3d3abba05bc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "apartments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apartment_id", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("timezone", sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apartment_id"),
    )
    op.create_index(op.f("ix_apartments_apartment_id"), "apartments", ["apartment_id"], unique=True)

    # Backfill known apartment IDs from existing operational tables.
    op.execute(
        """
        INSERT INTO apartments (apartment_id, timezone, created_at, updated_at)
        SELECT DISTINCT d.apartment_id, 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM devices d
        WHERE d.apartment_id IS NOT NULL
          AND d.apartment_id <> ''
          AND NOT EXISTS (
              SELECT 1 FROM apartments a WHERE a.apartment_id = d.apartment_id
          )
        """
    )

    op.execute(
        """
        INSERT INTO apartments (apartment_id, timezone, created_at, updated_at)
        SELECT DISTINCT c.apartment_id, 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM access_codes c
        WHERE c.apartment_id IS NOT NULL
          AND c.apartment_id <> ''
          AND NOT EXISTS (
              SELECT 1 FROM apartments a WHERE a.apartment_id = c.apartment_id
          )
        """
    )

    op.execute(
        """
        INSERT INTO apartments (apartment_id, timezone, created_at, updated_at)
        SELECT DISTINCT l.apartment_id, 'UTC', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM access_log l
        WHERE l.apartment_id IS NOT NULL
          AND l.apartment_id <> ''
          AND NOT EXISTS (
              SELECT 1 FROM apartments a WHERE a.apartment_id = l.apartment_id
          )
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_apartments_apartment_id"), table_name="apartments")
    op.drop_table("apartments")
