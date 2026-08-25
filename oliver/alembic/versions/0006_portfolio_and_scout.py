"""Add versioned portfolio insights and governed Scout candidates.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: Optional[Union[str, Sequence[str]]] = "0005"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create portfolio-report and Scout-candidate history."""
    op.create_table(
        "portfolio_insight_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("report", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("generated_by", sa.String(length=320), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("input_fingerprint", name="uq_portfolio_insight_input_fingerprint"),
    )
    op.create_table(
        "scout_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_system", sa.String(length=128), nullable=False),
        sa.Column("source_reference", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("proposed_owner", sa.String(length=320), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default=sa.text("'DISCOVERED'"), nullable=False),
        sa.Column("promoted_initiative_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_by", sa.String(length=320), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('DISCOVERED', 'REVIEWED', 'PROMOTED', 'DISMISSED')",
            name="ck_scout_candidate_status",
        ),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_scout_candidate_confidence"),
        sa.ForeignKeyConstraint(["promoted_initiative_id"], ["initiatives.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_system", "source_reference", "content_hash", name="uq_scout_candidate_source_content"),
    )
    op.create_index("ix_scout_candidates_status_discovered", "scout_candidates", ["status", "discovered_at"])


def downgrade() -> None:
    """Remove portfolio-report and Scout-candidate history."""
    op.drop_index("ix_scout_candidates_status_discovered", table_name="scout_candidates")
    op.drop_table("scout_candidates")
    op.drop_table("portfolio_insight_reports")
