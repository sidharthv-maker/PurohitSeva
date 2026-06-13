"""Initial schema — all six tables.

Revision ID: 001
Revises:
Create Date: 2026-06-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enum type ---------------------------------------------------------
    booking_status = postgresql.ENUM(
        "pending", "confirmed", "completed", "declined", "cancelled",
        name="bookingstatus",
        create_type = False,
    )
    booking_status.create(op.get_bind())

    # --- users -------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False, unique=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("hashed_password", sa.String(200), nullable=False),
        sa.Column("is_pandit", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # --- pandits -----------------------------------------------------------
    op.create_table(
        "pandits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("area", sa.String(200), nullable=False),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("languages", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("years_experience", sa.Integer(), nullable=True),
        sa.Column("rating", sa.Float(), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # --- services (catalogue) ----------------------------------------------
    op.create_table(
        "services",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("duration_slots", sa.Integer(), nullable=True),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("icon", sa.String(10), nullable=True),
    )

    # --- pandit_services (join table with price) ---------------------------
    op.create_table(
        "pandit_services",
        sa.Column("pandit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pandits.id"), primary_key=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), primary_key=True),
        sa.Column("price", sa.Integer(), nullable=False),
    )

    # --- bookings ----------------------------------------------------------
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pandit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pandits.id"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=False),
        sa.Column("status", booking_status, nullable=False, server_default="pending"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("slots", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_pandit_id", "bookings", ["pandit_id"])
    op.create_index("ix_bookings_status", "bookings", ["status"])

    # --- booking_slots (availability enforcement) --------------------------
    op.create_table(
        "booking_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pandit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pandits.id"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("slot", sa.String(20), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.UniqueConstraint("pandit_id", "date", "slot", name="uq_pandit_date_slot"),
    )

    # --- reviews -----------------------------------------------------------
    op.create_table(
        "reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False, unique=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("reviews")
    op.drop_table("booking_slots")
    op.drop_table("bookings")
    op.drop_table("pandit_services")
    op.drop_table("services")
    op.drop_table("pandits")
    op.drop_table("users")
    op.execute("DROP TYPE bookingstatus")
