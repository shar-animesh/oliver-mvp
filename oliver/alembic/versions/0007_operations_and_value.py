"""Add Sentinel measurements, alerts, and Realizer value tracking.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: Optional[Union[str, Sequence[str]]] = "0006"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create normalized metric observations and breach alerts."""
    op.create_table(
        "metric_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("metric_type", sa.String(length=16), nullable=False),
        sa.Column("unit", sa.String(length=64), nullable=False),
        sa.Column("direction", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("baseline", sa.Float(), nullable=True),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("metric_type IN ('SLO', 'VALUE')", name="ck_metric_definition_type"),
        sa.CheckConstraint("direction IN ('AT_LEAST', 'AT_MOST')", name="ck_metric_definition_direction"),
        sa.ForeignKeyConstraint(["initiative_id"], ["initiatives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("initiative_id", "name", name="uq_metric_definition_initiative_name"),
    )
    op.create_index("ix_metric_definitions_initiative_id", "metric_definitions", ["initiative_id"])
    op.create_table(
        "metric_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("metric_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=512), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["metric_id"], ["metric_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_metric_observation_idempotency_key"),
    )
    op.create_index(
        "ix_metric_observations_metric_observed",
        "metric_observations",
        ["metric_id", "observed_at"],
    )
    op.create_table(
        "operational_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'OPEN'"), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=320), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'ACKNOWLEDGED', 'RESOLVED')", name="ck_operational_alert_status"),
        sa.ForeignKeyConstraint(["initiative_id"], ["initiatives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["observation_id"], ["metric_observations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("observation_id", name="uq_operational_alert_observation"),
    )
    op.create_index(
        "ix_operational_alerts_initiative_status",
        "operational_alerts",
        ["initiative_id", "status"],
    )


def downgrade() -> None:
    """Remove normalized metric observations and breach alerts."""
    op.drop_index("ix_operational_alerts_initiative_status", table_name="operational_alerts")
    op.drop_table("operational_alerts")
    op.drop_index("ix_metric_observations_metric_observed", table_name="metric_observations")
    op.drop_table("metric_observations")
    op.drop_index("ix_metric_definitions_initiative_id", table_name="metric_definitions")
    op.drop_table("metric_definitions")
