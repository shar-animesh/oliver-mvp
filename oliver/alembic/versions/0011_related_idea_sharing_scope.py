"""Add explicit governance for cross-initiative semantic context.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Optional[Union[str, Sequence[str]]] = "0010"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Keep initiatives private until an authorized workflow opts them in."""
    op.add_column(
        "initiatives",
        sa.Column("related_idea_sharing_scope", sa.String(length=16), server_default="PRIVATE", nullable=False),
    )
    op.create_check_constraint(
        "ck_initiative_related_idea_sharing_scope",
        "initiatives",
        "related_idea_sharing_scope IN ('PRIVATE', 'INTERNAL')",
    )


def downgrade() -> None:
    """Remove explicit related-idea sharing governance."""
    op.drop_constraint("ck_initiative_related_idea_sharing_scope", "initiatives", type_="check")
    op.drop_column("initiatives", "related_idea_sharing_scope")
