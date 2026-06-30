"""add billing balance and transactions

Revision ID: bad4aefcfcf4
Revises: 7a8e9d0c1b2f
Create Date: 2026-06-30 14:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "bad4aefcfcf4"
down_revision: Union[str, None] = "7a8e9d0c1b2f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add balance_usd to organizations
    op.add_column(
        "organizations",
        sa.Column(
            "balance_usd",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.0"),
        ),
    )

    # Create billing_transactions table
    op.create_table(
        "billing_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("stripe_session_id", sa.String(), nullable=True),
        sa.Column("amount_usd", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_billing_transactions_id"),
        "billing_transactions",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_billing_transactions_stripe_session_id"),
        "billing_transactions",
        ["stripe_session_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_billing_transactions_stripe_session_id"),
        table_name="billing_transactions",
    )
    op.drop_index(
        op.f("ix_billing_transactions_id"),
        table_name="billing_transactions",
    )
    op.drop_table("billing_transactions")
    op.drop_column("organizations", "balance_usd")
