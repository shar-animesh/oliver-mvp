"""Add the non-transitioning DI5 monitoring outcome.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

from alembic import op

revision: str = "0009"
down_revision: Optional[Union[str, Sequence[str]]] = "0008"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Allow DI5 assessments to record monitoring without implying a transition."""
    op.drop_constraint("ck_assessment_gate_outcome", "canonical_assessments", type_="check")
    op.create_check_constraint(
        "ck_assessment_gate_outcome",
        "canonical_assessments",
        "gate_outcome IN ('ADVANCE', 'CONDITIONAL_ADVANCE', 'HOLD_FOR_EVIDENCE', 'DO_NOT_ADVANCE', 'CONTINUE_MONITORING')",
    )


def downgrade() -> None:
    """Map terminal monitoring history to the legacy non-advancing outcome."""
    op.drop_constraint("ck_assessment_gate_outcome", "canonical_assessments", type_="check")
    op.execute("UPDATE canonical_assessments SET gate_outcome = 'HOLD_FOR_EVIDENCE' WHERE gate_outcome = 'CONTINUE_MONITORING'")
    op.create_check_constraint(
        "ck_assessment_gate_outcome",
        "canonical_assessments",
        "gate_outcome IN ('ADVANCE', 'CONDITIONAL_ADVANCE', 'HOLD_FOR_EVIDENCE', 'DO_NOT_ADVANCE')",
    )
