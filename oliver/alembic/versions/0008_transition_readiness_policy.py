"""Separate transition readiness from the legacy score-derived gate.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Optional[Union[str, Sequence[str]]] = "0007"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Rename ambiguous fields and store the versioned criterion evaluation."""
    op.drop_constraint("ck_assessment_input_stage", "canonical_assessments", type_="check")
    op.drop_constraint("ck_assessment_assigned_stage", "canonical_assessments", type_="check")
    op.alter_column("canonical_assessments", "input_stage", new_column_name="current_stage")
    op.alter_column("canonical_assessments", "assigned_stage", new_column_name="recommended_next_stage")
    op.alter_column("canonical_assessments", "gate_decision", new_column_name="gate_outcome")
    op.alter_column("canonical_assessments", "recommended_next_stage", nullable=True)

    op.add_column("canonical_assessments", sa.Column("transition_target", sa.String(length=8), nullable=True))
    op.add_column("canonical_assessments", sa.Column("response_depth", sa.String(length=16), nullable=True))
    op.add_column("canonical_assessments", sa.Column("score_rationale", sa.Text(), nullable=True))
    op.add_column("canonical_assessments", sa.Column("transition_rationale", sa.Text(), nullable=True))
    op.add_column("canonical_assessments", sa.Column("transition_policy_version", sa.String(length=64), nullable=True))
    op.add_column(
        "canonical_assessments",
        sa.Column("criteria", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.execute(
        """
        UPDATE canonical_assessments
        SET
            transition_target = CASE current_stage
                WHEN 'DI1' THEN 'DI2'
                WHEN 'DI2' THEN 'DI3'
                WHEN 'DI3' THEN 'DI4'
                WHEN 'DI4' THEN 'DI5'
                ELSE NULL
            END,
            recommended_next_stage = CASE
                WHEN gate_outcome = 'GATE_PASS' THEN CASE current_stage
                    WHEN 'DI1' THEN 'DI2'
                    WHEN 'DI2' THEN 'DI3'
                    WHEN 'DI3' THEN 'DI4'
                    WHEN 'DI4' THEN 'DI5'
                    ELSE NULL
                END
                ELSE NULL
            END,
            gate_outcome = CASE gate_outcome
                WHEN 'GATE_PASS' THEN 'ADVANCE'
                WHEN 'COACHING_REJECT' THEN 'HOLD_FOR_EVIDENCE'
                WHEN 'NO_GO_RECOMMENDED' THEN 'DO_NOT_ADVANCE'
                ELSE gate_outcome
            END,
            response_depth = 'DETAILED',
            score_rationale = rationale,
            transition_rationale = 'Legacy score-derived result retained for history; reassessment is required under the transition policy.',
            transition_policy_version = 'legacy-score-policy',
            criteria = '[]'::jsonb
        """
    )

    op.alter_column("canonical_assessments", "response_depth", nullable=False)
    op.alter_column("canonical_assessments", "score_rationale", nullable=False)
    op.alter_column("canonical_assessments", "transition_rationale", nullable=False)
    op.alter_column("canonical_assessments", "transition_policy_version", nullable=False)
    op.alter_column("canonical_assessments", "criteria", nullable=False)
    op.drop_column("canonical_assessments", "rationale")

    op.create_check_constraint(
        "ck_assessment_current_stage",
        "canonical_assessments",
        "current_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
    )
    op.create_check_constraint(
        "ck_assessment_transition_target",
        "canonical_assessments",
        "transition_target IS NULL OR transition_target IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
    )
    op.create_check_constraint(
        "ck_assessment_recommended_stage",
        "canonical_assessments",
        "recommended_next_stage IS NULL OR recommended_next_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
    )
    op.create_check_constraint(
        "ck_assessment_gate_outcome",
        "canonical_assessments",
        "gate_outcome IN ('ADVANCE', 'CONDITIONAL_ADVANCE', 'HOLD_FOR_EVIDENCE', 'DO_NOT_ADVANCE')",
    )
    op.create_check_constraint(
        "ck_assessment_response_depth",
        "canonical_assessments",
        "response_depth IN ('BRIEF', 'STANDARD', 'DETAILED')",
    )


def downgrade() -> None:
    """Restore the legacy field shape without reconstructing discarded policy detail."""
    op.drop_constraint("ck_assessment_response_depth", "canonical_assessments", type_="check")
    op.drop_constraint("ck_assessment_gate_outcome", "canonical_assessments", type_="check")
    op.drop_constraint("ck_assessment_recommended_stage", "canonical_assessments", type_="check")
    op.drop_constraint("ck_assessment_transition_target", "canonical_assessments", type_="check")
    op.drop_constraint("ck_assessment_current_stage", "canonical_assessments", type_="check")

    op.add_column("canonical_assessments", sa.Column("rationale", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE canonical_assessments
        SET
            rationale = COALESCE(score_rationale, transition_rationale),
            recommended_next_stage = COALESCE(recommended_next_stage, current_stage),
            gate_outcome = CASE gate_outcome
                WHEN 'ADVANCE' THEN 'GATE_PASS'
                WHEN 'CONDITIONAL_ADVANCE' THEN 'GATE_PASS'
                WHEN 'HOLD_FOR_EVIDENCE' THEN 'COACHING_REJECT'
                WHEN 'DO_NOT_ADVANCE' THEN 'NO_GO_RECOMMENDED'
                ELSE gate_outcome
            END
        """
    )
    op.alter_column("canonical_assessments", "rationale", nullable=False)
    op.alter_column("canonical_assessments", "recommended_next_stage", nullable=False)

    op.drop_column("canonical_assessments", "criteria")
    op.drop_column("canonical_assessments", "transition_policy_version")
    op.drop_column("canonical_assessments", "transition_rationale")
    op.drop_column("canonical_assessments", "score_rationale")
    op.drop_column("canonical_assessments", "response_depth")
    op.drop_column("canonical_assessments", "transition_target")

    op.alter_column("canonical_assessments", "gate_outcome", new_column_name="gate_decision")
    op.alter_column("canonical_assessments", "recommended_next_stage", new_column_name="assigned_stage")
    op.alter_column("canonical_assessments", "current_stage", new_column_name="input_stage")
    op.create_check_constraint(
        "ck_assessment_input_stage",
        "canonical_assessments",
        "input_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
    )
    op.create_check_constraint(
        "ck_assessment_assigned_stage",
        "canonical_assessments",
        "assigned_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')",
    )
