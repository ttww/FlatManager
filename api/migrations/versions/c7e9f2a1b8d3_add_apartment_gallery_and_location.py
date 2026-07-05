"""add apartment gallery and location

Revision ID: c7e9f2a1b8d3
Revises: b4f7c9d2e1ab
Create Date: 2026-07-05 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7e9f2a1b8d3"
down_revision: Union[str, Sequence[str], None] = "b4f7c9d2e1ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("apartments", sa.Column("address_line1", sa.String(length=160), nullable=True))
    op.add_column("apartments", sa.Column("address_line2", sa.String(length=160), nullable=True))
    op.add_column("apartments", sa.Column("postal_code", sa.String(length=32), nullable=True))
    op.add_column("apartments", sa.Column("city", sa.String(length=120), nullable=True))
    op.add_column("apartments", sa.Column("country_code", sa.String(length=2), nullable=True))
    op.add_column("apartments", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("apartments", sa.Column("longitude", sa.Float(), nullable=True))

    op.create_table(
        "apartment_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("apartment_id", sa.String(length=100), nullable=False),
        sa.Column("storage_filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["apartment_id"], ["apartments.apartment_id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_filename"),
    )
    op.create_index(op.f("ix_apartment_images_apartment_id"), "apartment_images", ["apartment_id"], unique=False)
    op.create_index(op.f("ix_apartment_images_sort_order"), "apartment_images", ["sort_order"], unique=False)
    op.create_index(op.f("ix_apartment_images_storage_filename"), "apartment_images", ["storage_filename"], unique=True)

    op.add_column("apartments", sa.Column("guest_background_image_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_apartments_guest_background_image_id",
        "apartments",
        "apartment_images",
        ["guest_background_image_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_apartments_guest_background_image_id", "apartments", type_="foreignkey")
    op.drop_column("apartments", "guest_background_image_id")

    op.drop_index(op.f("ix_apartment_images_storage_filename"), table_name="apartment_images")
    op.drop_index(op.f("ix_apartment_images_sort_order"), table_name="apartment_images")
    op.drop_index(op.f("ix_apartment_images_apartment_id"), table_name="apartment_images")
    op.drop_table("apartment_images")

    op.drop_column("apartments", "longitude")
    op.drop_column("apartments", "latitude")
    op.drop_column("apartments", "country_code")
    op.drop_column("apartments", "city")
    op.drop_column("apartments", "postal_code")
    op.drop_column("apartments", "address_line2")
    op.drop_column("apartments", "address_line1")
