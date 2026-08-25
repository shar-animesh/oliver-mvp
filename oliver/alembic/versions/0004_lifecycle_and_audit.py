"""Add deterministic lifecycle transitions and append-only audit history.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: Optional[Union[str, Sequence[str]]] = "0003"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create lifecycle decision and immutable audit structures."""
    op.add_column(
        "initiatives",
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.execute("UPDATE initiatives SET stage_entered_at = updated_at")

    op.create_table(
        "lifecycle_transitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("assessment_run_id", sa.Uuid(), nullable=True),
        sa.Column("transition_type", sa.String(length=16), nullable=False),
        sa.Column("from_stage", sa.String(length=8), nullable=False),
        sa.Column("to_stage", sa.String(length=8), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False),
        sa.Column("expected_initiative_version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("proposed_by", sa.String(length=320), nullable=False),
        sa.Column("decided_by", sa.String(length=320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "transition_type IN ('ADVANCE', 'NO_GO', 'RETIRE', 'OVERRIDE', 'ROLLBACK', 'HOLD', 'RESUME')",
            name="ck_lifecycle_transition_type",
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPLIED', 'APPROVED', 'REJECTED', 'CANCELLED')",
            name="ck_lifecycle_transition_status",
        ),
        sa.CheckConstraint("from_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_lifecycle_transition_from_stage"),
        sa.CheckConstraint(
            "to_stage IS NULL OR to_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
            name="ck_lifecycle_transition_to_stage",
        ),
        sa.CheckConstraint("expected_initiative_version > 0", name="ck_lifecycle_transition_version_positive"),
        sa.ForeignKeyConstraint(["assessment_run_id"], ["canonical_assessments.run_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["initiative_id"], ["initiatives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_run_id", "transition_type", name="uq_lifecycle_transition_assessment_type"),
    )
    op.create_index(
        "ix_lifecycle_transitions_initiative_created",
        "lifecycle_transitions",
        ["initiative_id", "created_at"],
    )
    op.create_index("ix_lifecycle_transitions_pending", "lifecycle_transitions", ["status", "created_at"])

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=320), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "actor_type IN ('SYSTEM', 'USER', 'MANAGED_IDENTITY')",
            name="ck_audit_event_actor_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_correlation", "audit_events", ["correlation_id"])
    op.create_index("ix_audit_events_initiative_occurred", "audit_events", ["initiative_id", "occurred_at"])

    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    op.execute(
        """
        INSERT INTO audit_events (
            id, initiative_id, event_type, actor_type, actor_id,
            subject_type, subject_id, correlation_id, payload, occurred_at
        )
        SELECT
            assessment.run_id,
            assessment.initiative_id,
            'ASSESSMENT_RECORDED',
            'SYSTEM',
            'Oliver',
            'canonical_assessment',
            assessment.run_id::text,
            assessment.run_id::text,
            jsonb_build_object(
                'input_stage', assessment.input_stage,
                'assigned_stage', assessment.assigned_stage,
                'gate_decision', assessment.gate_decision,
                'composite_score', assessment.composite_score,
                'historical_backfill', true
            ),
            assessment.created_at
        FROM canonical_assessments AS assessment
        """
    )


def downgrade() -> None:
    """Remove lifecycle decision and audit structures."""
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_index("ix_audit_events_initiative_occurred", table_name="audit_events")
    op.drop_index("ix_audit_events_correlation", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_lifecycle_transitions_pending", table_name="lifecycle_transitions")
    op.drop_index("ix_lifecycle_transitions_initiative_created", table_name="lifecycle_transitions")
    op.drop_table("lifecycle_transitions")
    op.drop_column("initiatives", "stage_entered_at")
