"""Add ChatGPT guest grants."""

import sqlalchemy as sa
from alembic import context, op

revision = "e1f8b58da992"
down_revision = "c7e9f2a1b8d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "chatgpt_guest_grants"
    # Application startup can already have created this table via SQLModel.
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(table):
        return
    op.create_table(
        table,
        sa.Column("authorization_code_hash", sa.String(64), primary_key=True),
        sa.Column("access_code_id", sa.Integer(), nullable=False),
        sa.Column("access_code_fingerprint", sa.String(64), nullable=False),
        sa.Column("code_challenge", sa.String(43), nullable=False),
        sa.Column("client_id", sa.String(512), nullable=False),
        sa.Column("redirect_uri", sa.String(512), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("authorization_expires_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("token_hash", sa.String(64), unique=True),
        sa.Column("open_ticket_hash", sa.String(64)),
        sa.Column("open_ticket_expires_at", sa.DateTime()),
    )
    for column in ("access_code_id", "expires_at"):
        op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade() -> None:
    op.drop_table("chatgpt_guest_grants")
