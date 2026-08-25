"""Add canonical initiatives and versioned evidence.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-24 00:00:00.000000
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: Optional[Union[str, Sequence[str]]] = "0002"
branch_labels: Optional[Union[str, Sequence[str]]] = None
depends_on: Optional[Union[str, Sequence[str]]] = None


def upgrade() -> None:
    """Create the initiative aggregate and normalized evidence ledger."""
    op.create_table(
        "initiatives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("owner_email", sa.String(length=320), nullable=True),
        sa.Column("current_stage", sa.String(length=8), server_default=sa.text("'DI1'"), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), server_default=sa.text("'Assessed'"), nullable=False),
        sa.Column("is_on_hold", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hold_reason", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("current_stage IN ('DI1', 'DI2', 'DI3', 'DI4', 'DI5')", name="ck_initiative_current_stage"),
        sa.CheckConstraint("version > 0", name="ck_initiative_version_positive"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("email_threads", sa.Column("initiative_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_email_threads_initiative_id_initiatives",
        "email_threads",
        "initiatives",
        ["initiative_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_email_threads_initiative_id", "email_threads", ["initiative_id"])

    op.execute(
        """
        INSERT INTO initiatives (id, title, owner_email, current_stage, lifecycle_state, created_at, updated_at)
        SELECT
            thread.id,
            LEFT(COALESCE(NULLIF(thread.subject, ''), 'Untitled initiative'), 200),
            thread.participant_email,
            latest.assigned_stage,
            latest.lifecycle_state,
            thread.created_at,
            thread.updated_at
        FROM email_threads AS thread
        JOIN LATERAL (
            SELECT assessment.assigned_stage, assessment.lifecycle_state
            FROM oliver_runs AS run
            JOIN canonical_assessments AS assessment ON assessment.run_id = run.id
            WHERE run.thread_id = thread.id
            ORDER BY assessment.created_at DESC
            LIMIT 1
        ) AS latest ON true
        """
    )
    op.execute("UPDATE email_threads SET initiative_id = id WHERE id IN (SELECT id FROM initiatives)")

    op.create_table(
        "attachment_blobs",
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=False),
        sa.Column("extraction_status", sa.String(length=32), server_default=sa.text("'PENDING'"), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("size_bytes >= 0", name="ck_attachment_blob_size_nonnegative"),
        sa.CheckConstraint(
            "extraction_status IN ('PENDING', 'SUCCEEDED', 'FAILED', 'UNSUPPORTED')",
            name="ck_attachment_blob_extraction_status",
        ),
        sa.PrimaryKeyConstraint("content_hash"),
    )
    op.create_table(
        "email_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("provider_attachment_id", sa.String(length=512), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("blob_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["blob_hash"], ["attachment_blobs.content_hash"]),
        sa.ForeignKeyConstraint(["message_id"], ["email_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "provider_attachment_id", name="uq_email_attachment_provider_id"),
    )
    op.create_index("ix_email_attachments_message", "email_attachments", ["message_id"])

    op.create_table(
        "evidence_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("attachment_id", sa.Uuid(), nullable=True),
        sa.Column("external_source_ref", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("source_type IN ('MESSAGE', 'ATTACHMENT', 'ADMIN', 'SCOUT')", name="ck_evidence_item_source_type"),
        sa.CheckConstraint(
            "(source_type = 'MESSAGE' AND message_id IS NOT NULL AND attachment_id IS NULL) OR "
            "(source_type = 'ATTACHMENT' AND attachment_id IS NOT NULL AND message_id IS NULL) OR "
            "(source_type IN ('ADMIN', 'SCOUT') AND message_id IS NULL AND attachment_id IS NULL)",
            name="ck_evidence_item_source_reference",
        ),
        sa.ForeignKeyConstraint(["attachment_id"], ["email_attachments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiative_id"], ["initiatives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["email_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("initiative_id", "attachment_id", name="uq_evidence_item_initiative_attachment"),
        sa.UniqueConstraint("initiative_id", "message_id", name="uq_evidence_item_initiative_message"),
    )
    op.create_index("ix_evidence_items_initiative_created", "evidence_items", ["initiative_id", "created_at"])
    op.create_table(
        "evidence_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("trigger_message_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version > 0", name="ck_evidence_version_positive"),
        sa.ForeignKeyConstraint(["initiative_id"], ["initiatives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["trigger_message_id"], ["email_messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("initiative_id", "source_fingerprint", name="uq_evidence_version_fingerprint"),
        sa.UniqueConstraint("initiative_id", "version", name="uq_evidence_version_number"),
    )
    op.create_table(
        "evidence_version_items",
        sa.Column("evidence_version_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_item_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["evidence_item_id"], ["evidence_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["evidence_version_id"], ["evidence_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_version_id", "evidence_item_id"),
    )

    op.add_column("canonical_assessments", sa.Column("initiative_id", sa.Uuid(), nullable=True))
    op.add_column("canonical_assessments", sa.Column("evidence_version_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_canonical_assessments_initiative_id_initiatives",
        "canonical_assessments",
        "initiatives",
        ["initiative_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_canonical_assessments_evidence_version_id_evidence_versions",
        "canonical_assessments",
        "evidence_versions",
        ["evidence_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_canonical_assessments_initiative_id", "canonical_assessments", ["initiative_id"])

    op.execute(
        """
        INSERT INTO evidence_items (id, initiative_id, source_type, message_id, content_hash, created_at)
        SELECT message.id, thread.initiative_id, 'MESSAGE', message.id, md5(COALESCE(message.content_html, '')), message.created_at
        FROM email_messages AS message
        JOIN email_threads AS thread ON thread.id = message.thread_id
        WHERE thread.initiative_id IS NOT NULL AND message.direction = 'INBOUND'
        """
    )
    op.execute(
        """
        INSERT INTO evidence_versions (id, initiative_id, version, source_fingerprint, trigger_message_id, created_at)
        SELECT
            initiative.id,
            initiative.id,
            1,
            md5(string_agg(item.id::text, ',' ORDER BY item.created_at, item.id)),
            (
                SELECT message.id
                FROM email_messages AS message
                JOIN email_threads AS thread ON thread.id = message.thread_id
                WHERE thread.initiative_id = initiative.id AND message.direction = 'INBOUND'
                ORDER BY message.received_at DESC
                LIMIT 1
            ),
            initiative.updated_at
        FROM initiatives AS initiative
        JOIN evidence_items AS item ON item.initiative_id = initiative.id
        GROUP BY initiative.id
        """
    )
    op.execute(
        """
        INSERT INTO evidence_version_items (evidence_version_id, evidence_item_id)
        SELECT version.id, item.id
        FROM evidence_versions AS version
        JOIN evidence_items AS item ON item.initiative_id = version.initiative_id
        """
    )
    op.execute(
        """
        UPDATE canonical_assessments AS assessment
        SET initiative_id = thread.initiative_id,
            evidence_version_id = version.id
        FROM oliver_runs AS run
        JOIN email_threads AS thread ON thread.id = run.thread_id
        LEFT JOIN evidence_versions AS version ON version.initiative_id = thread.initiative_id
        WHERE assessment.run_id = run.id
        """
    )


def downgrade() -> None:
    """Remove the initiative aggregate and evidence ledger."""
    op.drop_index("ix_canonical_assessments_initiative_id", table_name="canonical_assessments")
    op.drop_constraint(
        "fk_canonical_assessments_evidence_version_id_evidence_versions",
        "canonical_assessments",
        type_="foreignkey",
    )
    op.drop_constraint("fk_canonical_assessments_initiative_id_initiatives", "canonical_assessments", type_="foreignkey")
    op.drop_column("canonical_assessments", "evidence_version_id")
    op.drop_column("canonical_assessments", "initiative_id")
    op.drop_table("evidence_version_items")
    op.drop_table("evidence_versions")
    op.drop_index("ix_evidence_items_initiative_created", table_name="evidence_items")
    op.drop_table("evidence_items")
    op.drop_index("ix_email_attachments_message", table_name="email_attachments")
    op.drop_table("email_attachments")
    op.drop_table("attachment_blobs")
    op.drop_index("ix_email_threads_initiative_id", table_name="email_threads")
    op.drop_constraint("fk_email_threads_initiative_id_initiatives", "email_threads", type_="foreignkey")
    op.drop_column("email_threads", "initiative_id")
    op.drop_table("initiatives")
