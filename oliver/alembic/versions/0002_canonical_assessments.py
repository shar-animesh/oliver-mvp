"""Add canonical assessment records.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Optional[Union[str, Sequence[str]]] = "0001"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create one versioned canonical assessment per Oliver run."""
    op.create_table(
        "canonical_assessments",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("input_stage", sa.String(length=8), nullable=False),
        sa.Column("composite_score", sa.Integer(), nullable=True),
        sa.Column("assigned_stage", sa.String(length=8), nullable=False),
        sa.Column("gate_decision", sa.String(length=32), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("composite_confidence", sa.Float(), nullable=True),
        sa.Column("lowest_confidence_dimension", sa.String(length=64), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("rating", sa.String(length=32), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("weight_set_version", sa.String(length=64), nullable=False),
        sa.Column("dimensions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("composite_score IS NULL OR composite_score BETWEEN 0 AND 100", name="ck_assessment_score_range"),
        sa.CheckConstraint(
            "composite_confidence IS NULL OR composite_confidence BETWEEN 0 AND 1",
            name="ck_assessment_confidence_range",
        ),
        sa.CheckConstraint("input_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_assessment_input_stage"),
        sa.CheckConstraint("assigned_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_assessment_assigned_stage"),
        sa.ForeignKeyConstraint(["run_id"], ["oliver_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    """Remove canonical assessment records."""
    op.drop_table("canonical_assessments")
