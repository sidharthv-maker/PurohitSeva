"""Add awaiting_payment/expired status enum values + payments table.

Revision ID: 002
Revises: 001
Create Date: 2026-06-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ALTER TYPE … ADD VALUE cannot run inside a transaction in PostgreSQL < 12.
    # We commit the current Alembic transaction, run the DDL, then begin a fresh
    # one so the rest of the migration runs transactionally as normal.
    bind.execute(sa.text("COMMIT"))
    bind.execute(sa.text(
        "ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'awaiting_payment'"
    ))
    bind.execute(sa.text(
        "ALTER TYPE bookingstatus ADD VALUE IF NOT EXISTS 'expired'"
    ))
    bind.execute(sa.text("BEGIN"))

    # --- payment deadline on bookings -----------------------------------------
    op.add_column(
        "bookings",
        sa.Column("payment_due_at", sa.DateTime(timezone=True), nullable=True),
    )

    # --- payments table --------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "booking_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bookings.id"),
            nullable=False,
        ),
        sa.Column("razorpay_order_id", sa.String(100), nullable=False, unique=True),
        sa.Column("razorpay_payment_id", sa.String(100), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=False),   # paise (₹ × 100)
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="created",
        ),  # created | paid | failed
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])


def downgrade() -> None:
    # Reset bookings that are in the new status values before removing them.
    # PostgreSQL has no DROP VALUE — the enum values survive but stay unused.
    op.execute(sa.text(
        "UPDATE bookings SET status = 'cancelled' "
        "WHERE status IN ('awaiting_payment', 'expired')"
    ))
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.drop_table("payments")
    op.drop_column("bookings", "payment_due_at")
