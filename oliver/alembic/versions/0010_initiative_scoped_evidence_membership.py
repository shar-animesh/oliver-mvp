"""Enforce initiative-scoped evidence-version membership.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-25 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Optional[Union[str, Sequence[str]]] = "0009"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Ensure every evidence snapshot contains evidence from its own initiative."""
    op.create_unique_constraint("uq_evidence_items_id_initiative", "evidence_items", ["id", "initiative_id"])
    op.create_unique_constraint("uq_evidence_versions_id_initiative", "evidence_versions", ["id", "initiative_id"])
    op.add_column("evidence_version_items", sa.Column("initiative_id", sa.Uuid(), nullable=True))
    op.execute(
        """
        UPDATE evidence_version_items AS membership
        SET initiative_id = version.initiative_id
        FROM evidence_versions AS version
        WHERE version.id = membership.evidence_version_id
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM evidence_version_items AS membership
                JOIN evidence_items AS item ON item.id = membership.evidence_item_id
                WHERE item.initiative_id <> membership.initiative_id
            ) THEN
                RAISE EXCEPTION 'Cross-initiative evidence membership must be resolved before migration 0010';
            END IF;
        END $$
        """
    )
    op.alter_column("evidence_version_items", "initiative_id", nullable=False)
    op.drop_constraint(
        "evidence_version_items_evidence_version_id_fkey",
        "evidence_version_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "evidence_version_items_evidence_item_id_fkey",
        "evidence_version_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_evidence_version_items_version_initiative",
        "evidence_version_items",
        "evidence_versions",
        ["evidence_version_id", "initiative_id"],
        ["id", "initiative_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_evidence_version_items_item_initiative",
        "evidence_version_items",
        "evidence_items",
        ["evidence_item_id", "initiative_id"],
        ["id", "initiative_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Restore the legacy membership table shape."""
    op.drop_constraint(
        "fk_evidence_version_items_item_initiative",
        "evidence_version_items",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_evidence_version_items_version_initiative",
        "evidence_version_items",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "evidence_version_items_evidence_item_id_fkey",
        "evidence_version_items",
        "evidence_items",
        ["evidence_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "evidence_version_items_evidence_version_id_fkey",
        "evidence_version_items",
        "evidence_versions",
        ["evidence_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_column("evidence_version_items", "initiative_id")
    op.drop_constraint("uq_evidence_versions_id_initiative", "evidence_versions", type_="unique")
    op.drop_constraint("uq_evidence_items_id_initiative", "evidence_items", type_="unique")
