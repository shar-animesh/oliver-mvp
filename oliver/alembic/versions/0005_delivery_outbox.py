"""Add durable email delivery outbox and idempotent result receipts.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Optional[Union[str, Sequence[str]]] = "0004"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create delivery state and result-attempt history."""
    op.create_table(
        "delivery_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("outbound_message_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED', 'UNKNOWN')", name="ck_delivery_outbox_status"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_delivery_outbox_attempt_count_nonnegative"),
        sa.ForeignKeyConstraint(["outbound_message_id"], ["email_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["oliver_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("outbound_message_id", name="uq_delivery_outbox_message"),
        sa.UniqueConstraint("run_id", name="uq_delivery_outbox_run"),
    )
    op.create_index(
        "ix_delivery_outbox_status_next_attempt",
        "delivery_outbox",
        ["status", "next_attempt_at"],
    )
    op.create_table(
        "delivery_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("outcome IN ('SENT', 'FAILED')", name="ck_delivery_attempt_outcome"),
        sa.ForeignKeyConstraint(["delivery_id"], ["delivery_outbox.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_delivery_attempt_idempotency_key"),
    )
    op.create_index(
        "ix_delivery_attempts_delivery_created",
        "delivery_attempts",
        ["delivery_id", "created_at"],
    )

    op.execute(
        """
        INSERT INTO delivery_outbox (
            id, run_id, outbound_message_id, status, attempt_count,
            next_attempt_at, created_at, updated_at
        )
        SELECT run.id, run.id, message.id, 'UNKNOWN', 0, run.created_at, run.created_at, run.created_at
        FROM oliver_runs AS run
        JOIN email_messages AS message
          ON message.internet_message_id = 'oliver-run:' || run.id::text
        WHERE run.action = 'SEND_EMAIL'
        """
    )


def downgrade() -> None:
    """Remove delivery state and attempt history."""
    op.drop_index("ix_delivery_attempts_delivery_created", table_name="delivery_attempts")
    op.drop_table("delivery_attempts")
    op.drop_index("ix_delivery_outbox_status_next_attempt", table_name="delivery_outbox")
    op.drop_table("delivery_outbox")
